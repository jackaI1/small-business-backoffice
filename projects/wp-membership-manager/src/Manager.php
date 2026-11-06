<?php
namespace WPMM;

use InvalidArgumentException;

final class Manager {
    public function __construct(private Store $store, private string $today) { self::date($today); }
    private static function text(mixed $value, string $label, int $max = 200): string {
        if (!is_scalar($value)) { throw new InvalidArgumentException("Invalid $label."); }
        $value = trim((string)$value);
        if ($value === '' || strlen($value) > $max || preg_match('/[\x00-\x1f\x7f]/', $value)) { throw new InvalidArgumentException("Invalid $label."); }
        return $value;
    }
    private static function id(mixed $id): string {
        $id = self::text($id, 'record ID', 80);
        if (!preg_match('/^[a-zA-Z0-9_-]+$/D', $id)) { throw new InvalidArgumentException('IDs use letters, numbers, hyphens or underscores.'); }
        return $id;
    }
    private static function date(mixed $date): string {
        $date = self::text($date, 'date', 10);
        $parsed = \DateTimeImmutable::createFromFormat('!Y-m-d', $date);
        if (!$parsed || $parsed->format('Y-m-d') !== $date) { throw new InvalidArgumentException('Use a real date in YYYY-MM-DD format.'); }
        return $date;
    }
    public static function cents(string $value): int {
        if (!preg_match('/^(0|[1-9][0-9]{0,6})(?:\.([0-9]{1,2}))?$/D', $value, $m)) { throw new InvalidArgumentException('Use an amount from 0 to 9999999.99 with at most two decimal places.'); }
        return (int)$m[1] * 100 + (int)str_pad($m[2] ?? '', 2, '0');
    }
    private function requireRecord(string $kind, string $id): array {
        return $this->store->get($kind, self::id($id)) ?? throw new InvalidArgumentException("Unknown $kind ID: $id.");
    }
    public function records(string $kind): array { return $this->store->all($kind); }
    public function saveMember(array $input): void {
        $this->store->atomic(function() use ($input) { $this->writeMember($input); });
    }
    private function writeMember(array $input, bool $import = false): void {
        $id = self::id($input['id'] ?? ''); $email = strtolower(self::text($input['email'] ?? '', 'email', 254));
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) { throw new InvalidArgumentException('Invalid email address.'); }
        foreach ($this->store->all('member') as $member) {
            if ($member['email'] === $email && $member['id'] !== $id) { throw new InvalidArgumentException('This email already belongs to another member ID.'); }
        }
        if (!is_bool($input['consent'] ?? null)) { throw new InvalidArgumentException('Email consent must be explicit.'); }
        $old = $this->store->get('member', $id);
        $expires = self::date($input['expires'] ?? '');
        // Renewal receipts remain authoritative when older exports are imported again.
        foreach ($this->store->all('renewal') as $renewal) {
            if ($renewal['member'] === $id) { $expires = max($expires, $renewal['expires']); }
        }
        $this->store->put('member', $id, [
            'id'=>$id, 'name'=>self::text($input['name'] ?? '', 'name'), 'email'=>$email,
            'level'=>self::text($input['level'] ?? '', 'membership level', 80), 'expires'=>$expires,
            'consent'=>($old['unsubscribed'] ?? false) ? false : $input['consent'],
            'unsubscribed'=>$old['unsubscribed'] ?? false, 'source'=>$import ? 'Salesforce CSV' : ($old['source'] ?? 'admin'),
        ]);
    }
    public function renew(string $memberId, string $receipt, string $amount): void {
        $this->store->atomic(function() use ($memberId, $receipt, $amount) {
            $member = $this->requireRecord('member', $memberId); $receipt = self::id($receipt); $cents = self::cents($amount);
            if ($old = $this->store->get('renewal', $receipt)) {
                if ($old['member'] !== $memberId || $old['cents'] !== $cents) { throw new InvalidArgumentException('Receipt already used for a different renewal.'); }
                return;
            }
            $expires = (new \DateTimeImmutable(max($this->today, $member['expires'])))->modify('+1 year')->format('Y-m-d');
            $this->store->put('renewal', $receipt, ['id'=>$receipt,'member'=>$memberId,'date'=>$this->today,'cents'=>$cents,'expires'=>$expires]);
            $member['expires'] = $expires; $this->store->put('member', $memberId, $member);
        });
    }
    public function saveEvent(array $input): void {
        $this->store->atomic(function() use ($input) {
            $id = self::id($input['id'] ?? ''); $capacity = filter_var($input['capacity'] ?? null, FILTER_VALIDATE_INT, ['options'=>['min_range'=>1,'max_range'=>100000]]);
            if ($capacity === false) { throw new InvalidArgumentException('Capacity must be a whole number from 1 to 100000.'); }
            if ($this->registered($id) > $capacity) { throw new InvalidArgumentException('Capacity cannot be below existing registrations.'); }
            $this->store->put('event', $id, ['id'=>$id,'name'=>self::text($input['name'] ?? '', 'event name'),'date'=>self::date($input['date'] ?? ''),'capacity'=>$capacity]);
        });
    }
    private function registered(string $event): int { return count(array_filter($this->store->all('registration'), fn($r)=>$r['event'] === $event)); }
    public function register(string $eventId, string $memberId): void {
        $this->store->atomic(function() use ($eventId, $memberId) {
            $event = $this->requireRecord('event', $eventId); $this->requireRecord('member', $memberId); $key = hash('sha256', "$eventId:$memberId");
            if ($this->store->get('registration', $key)) { return; }
            if ($this->registered($eventId) >= $event['capacity']) { throw new InvalidArgumentException('Event is full.'); }
            $this->store->put('registration', $key, ['id'=>$key,'event'=>$eventId,'member'=>$memberId,'date'=>$this->today]);
        });
    }
    public function saveSponsor(array $input): void { $this->store->atomic(function() use ($input) { $this->writeSponsor($input); }); }
    private function writeSponsor(array $input): void {
        $id = self::id($input['id'] ?? ''); $event = $this->requireRecord('event', (string)($input['event'] ?? ''));
        $amount = self::cents((string)($input['amount'] ?? '')); $paid = self::cents((string)($input['paid'] ?? ''));
        if ($paid > $amount) { throw new InvalidArgumentException('Paid amount cannot exceed the sponsorship agreement.'); }
        $this->store->put('sponsor', $id, ['id'=>$id,'name'=>self::text($input['name'] ?? '', 'sponsor name'),'event'=>$event['id'],'cents'=>$amount,'paid_cents'=>$paid,'agreement'=>self::text($input['agreement'] ?? '', 'agreement', 2000)]);
    }
    public function segment(string $segment): array {
        if (!in_array($segment, ['all','active','due','expired'], true)) { throw new InvalidArgumentException('Unknown campaign segment.'); }
        $soon = (new \DateTimeImmutable($this->today))->modify('+30 days')->format('Y-m-d');
        return array_values(array_filter($this->store->all('member'), fn($m)=>$m['consent'] && match($segment) {
            'active'=>$m['expires'] >= $this->today, 'due'=>$m['expires'] >= $this->today && $m['expires'] <= $soon,
            'expired'=>$m['expires'] < $this->today, default=>true,
        }));
    }
    public function createCampaign(string $subject, string $html, string $segment): string {
        return $this->store->atomic(function() use ($subject, $html, $segment) {
            $subject = self::text($subject, 'subject', 200);
            if (trim(strip_tags($html)) === '' || strlen($html) > 50000) { throw new InvalidArgumentException('Email needs a message of at most 50000 bytes.'); }
            $members = $this->segment($segment); $id = bin2hex(random_bytes(12));
            $this->store->put('campaign', $id, ['id'=>$id,'subject'=>$subject,'html'=>$html,'segment'=>$segment,'date'=>$this->today,'recipients'=>count($members)]);
            foreach ($members as $member) {
                $key = "$id-{$member['id']}";
                $this->store->put('delivery', $key, ['id'=>$key,'campaign'=>$id,'member'=>$member['id'],'email'=>$member['email'],'name'=>$member['name'],'token'=>bin2hex(random_bytes(32)),'status'=>'pending','opened'=>false]);
            }
            return $id;
        });
    }
    public function deliveries(string $campaign): array { return array_values(array_filter($this->store->all('delivery'), fn($d)=>$d['campaign'] === $campaign)); }
    public function send(string $id, callable $mailer, string $baseUrl): int {
        // Serialize a bounded batch. A crash leaves 'sending' for manual reconciliation, never an automatic duplicate.
        return $this->store->atomic(function() use ($id, $mailer, $baseUrl) {
            $campaign = $this->requireRecord('campaign', $id); $sent = 0; $attempted = 0;
            $deliveries = $this->deliveries($id);
            usort($deliveries, fn($a,$b)=>(int)($a['status'] !== 'pending') <=> (int)($b['status'] !== 'pending'));
            foreach ($deliveries as $delivery) {
                if (!in_array($delivery['status'], ['pending','failed'], true)) { continue; }
                if (++$attempted > 100) { break; }
                $member = $this->requireRecord('member', $delivery['member']);
                if (!$member['consent'] || $member['email'] !== $delivery['email']) {
                    $delivery['status'] = 'skipped'; $this->store->put('delivery', $delivery['id'], $delivery); continue;
                }
                $delivery['status'] = 'sending'; $this->store->put('delivery', $delivery['id'], $delivery);
                $open = htmlspecialchars($baseUrl.'/?wpmm_open='.$delivery['token'], ENT_QUOTES, 'UTF-8');
                $unsubscribe = htmlspecialchars($baseUrl.'/?wpmm_unsubscribe='.$delivery['token'], ENT_QUOTES, 'UTF-8');
                $html = str_replace('{{name}}', htmlspecialchars($delivery['name'], ENT_QUOTES, 'UTF-8'), $campaign['html']);
                $html .= '<p><a href="'.$unsubscribe.'">Unsubscribe from membership emails</a></p><img src="'.$open.'" width="1" height="1" alt="">';
                try { $ok = (bool)$mailer($delivery['email'], $campaign['subject'], $html); } catch (\Throwable) { $ok = false; }
                $delivery['status'] = $ok ? 'sent' : 'failed'; $this->store->put('delivery', $delivery['id'], $delivery); $sent += (int)$ok;
            }
            return $sent;
        }, false);
    }
    private function tokenDelivery(string $token): ?array {
        if (!preg_match('/^[a-f0-9]{64}$/D', $token)) { return null; }
        foreach ($this->store->all('delivery') as $delivery) { if (hash_equals($delivery['token'], $token)) { return $delivery; } }
        return null;
    }
    public function validToken(string $token): bool { return $this->tokenDelivery($token) !== null; }
    public function open(string $token): bool {
        return $this->store->atomic(function() use ($token) {
            $delivery = $this->tokenDelivery($token); if (!$delivery || $delivery['status'] !== 'sent') { return false; }
            $delivery['opened'] = true; $this->store->put('delivery', $delivery['id'], $delivery); return true;
        });
    }
    public function unsubscribe(string $token): bool {
        return $this->store->atomic(function() use ($token) {
            $delivery = $this->tokenDelivery($token); if (!$delivery) { return false; }
            $member = $this->requireRecord('member', $delivery['member']); $member['consent'] = false; $member['unsubscribed'] = true;
            $this->store->put('member', $member['id'], $member); return true;
        });
    }
    public function importCsv(string $csv): int {
        if (strlen($csv) > 1048576) { throw new InvalidArgumentException('CSV must be at most 1 MiB.'); }
        $handle = fopen('php://temp', 'r+'); fwrite($handle, $csv); rewind($handle);
        try {
            $headers = fgetcsv($handle, 0, ',', '"', '');
            if ($headers) { $headers[0] = preg_replace('/^\xEF\xBB\xBF/', '', $headers[0]); }
            $required = ['Record Type','Record ID','Name','Email','Level','Expires On','Email Consent','Event ID','Amount','Paid Amount','Agreement'];
            $contactHeaders = ['Contact ID','Full Name','Email','Membership Level','Membership Expiry','Email Opt Out'];
            $sponsorHeaders = ['Opportunity ID','Account Name','Event ID','Amount','Amount Paid','Agreement'];
            if (!$headers || count(array_unique($headers)) !== count($headers)) { throw new InvalidArgumentException('CSV needs unique detail-report headers.'); }
            $format = !array_diff($required, $headers) ? 'normalized' : (!array_diff($contactHeaders, $headers) ? 'contact' : (!array_diff($sponsorHeaders, $headers) ? 'opportunity' : 'invalid'));
            if ($format === 'invalid') { throw new InvalidArgumentException('CSV needs the documented contact, opportunity or combined detail-report headers.'); }
            $rows = []; $seen = []; $line = 1;
            while (($cells = fgetcsv($handle, 0, ',', '"', '')) !== false) {
                ++$line; if ($cells === [null]) { continue; }
                if (count($cells) !== count($headers) || count($rows) >= 2000) { throw new InvalidArgumentException("Invalid column count or more than 2000 rows at row $line."); }
                $row = array_combine($headers, array_map('trim', $cells));
                if ($format === 'contact') {
                    if (!in_array(strtolower($row['Email Opt Out']), ['true','false','1','0'], true)) { throw new InvalidArgumentException("Row $line: Email Opt Out must be true or false."); }
                    $row = ['Record Type'=>'member','Record ID'=>$row['Contact ID'],'Name'=>$row['Full Name'],'Email'=>$row['Email'],'Level'=>$row['Membership Level'],'Expires On'=>$row['Membership Expiry'],'Email Consent'=>in_array(strtolower($row['Email Opt Out']), ['true','1'], true) ? 'no' : 'yes'];
                } elseif ($format === 'opportunity') {
                    $row = ['Record Type'=>'sponsor','Record ID'=>$row['Opportunity ID'],'Name'=>$row['Account Name'],'Event ID'=>$row['Event ID'],'Amount'=>$row['Amount'],'Paid Amount'=>$row['Amount Paid'],'Agreement'=>$row['Agreement']];
                }
                $key = $row['Record Type'].':'.$row['Record ID'];
                if (isset($seen[$key])) { throw new InvalidArgumentException("Duplicate ID at row $line."); }
                $seen[$key] = true; $rows[$line] = $row;
            }
            return $this->store->atomic(function() use ($rows) {
                foreach ($rows as $line=>$r) {
                    try {
                        if ($r['Record Type'] === 'member') {
                            if (!in_array($r['Email Consent'], ['yes','no'], true)) { throw new InvalidArgumentException('Email Consent must be yes or no.'); }
                            $this->writeMember(['id'=>$r['Record ID'],'name'=>$r['Name'],'email'=>$r['Email'],'level'=>$r['Level'],'expires'=>$r['Expires On'],'consent'=>$r['Email Consent'] === 'yes'], true);
                        } elseif ($r['Record Type'] === 'sponsor') {
                            $this->writeSponsor(['id'=>$r['Record ID'],'name'=>$r['Name'],'event'=>$r['Event ID'],'amount'=>$r['Amount'],'paid'=>$r['Paid Amount'],'agreement'=>$r['Agreement']]);
                        } else { throw new InvalidArgumentException('Record Type must be member or sponsor.'); }
                    } catch (InvalidArgumentException $e) { throw new InvalidArgumentException("Row $line: ".$e->getMessage()); }
                }
                return count($rows);
            });
        } finally { fclose($handle); }
    }
    /** Aggregate-only CSV for sharing a snapshot without exposing member records. */
    public function reportCsv(): string {
        $stream = fopen('php://temp', 'w+');
        fputcsv($stream, ['Metric', 'Value', 'Unit'], ',', '"', '');
        foreach ($this->report() as $key => $value) {
            $money = str_ends_with($key, '_cents');
            $label = $money ? substr($key, 0, -6) : $key;
            fputcsv($stream, [str_replace('_', ' ', $label), $money ? number_format($value / 100, 2, '.', '') : (string)$value, $money ? 'CAD' : 'count'], ',', '"', '');
        }
        rewind($stream); $csv = stream_get_contents($stream); fclose($stream);
        return $csv;
    }
    public function report(): array {
        $members = $this->store->all('member'); $renewals = $this->store->all('renewal'); $sponsors = $this->store->all('sponsor'); $deliveries = $this->store->all('delivery');
        $pledged = array_sum(array_column($sponsors, 'cents')); $paid = array_sum(array_column($sponsors, 'paid_cents'));
        return ['members'=>count($members),'active'=>count(array_filter($members, fn($m)=>$m['expires'] >= $this->today)),
            'due'=>count(array_filter($members, fn($m)=>$m['expires'] >= $this->today && $m['expires'] <= (new \DateTimeImmutable($this->today))->modify('+30 days')->format('Y-m-d'))),
            'renewals'=>count($renewals),'renewed_members'=>count(array_unique(array_column($renewals, 'member'))),'renewal_cents'=>array_sum(array_column($renewals,'cents')),
            'registrations'=>count($this->store->all('registration')),'sponsor_cents'=>$pledged,'sponsor_paid_cents'=>$paid,'sponsor_outstanding_cents'=>$pledged-$paid,
            'sent'=>count(array_filter($deliveries,fn($d)=>$d['status'] === 'sent')),'opened'=>count(array_filter($deliveries,fn($d)=>$d['opened'])),
            'failed'=>count(array_filter($deliveries,fn($d)=>$d['status'] === 'failed'))];
    }
}
