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
            $receipt = self::id($receipt); $cents = self::cents($amount);
            $this->recordRenewal($memberId, $receipt, $cents, 'admin');
        });
    }
    /** Shared by manual receipts and paid card renewals. A receipt ID is recorded once. */
    private function recordRenewal(string $memberId, string $receipt, int $cents, string $source): void {
        $member = $this->requireRecord('member', $memberId);
        if ($old = $this->store->get('renewal', $receipt)) {
            if ($old['member'] !== $memberId || $old['cents'] !== $cents) { throw new InvalidArgumentException('Receipt already used for a different renewal.'); }
            return;
        }
        $expires = (new \DateTimeImmutable(max($this->today, $member['expires'])))->modify('+1 year')->format('Y-m-d');
        $this->store->put('renewal', $receipt, ['id'=>$receipt,'member'=>$memberId,'date'=>$this->today,'cents'=>$cents,'expires'=>$expires,'source'=>$source,'refunded_cents'=>0]);
        $member['expires'] = $expires; $this->store->put('member', $memberId, $member);
    }
    public function saveEvent(array $input): void {
        $this->store->atomic(function() use ($input) {
            $id = self::id($input['id'] ?? ''); $capacity = filter_var($input['capacity'] ?? null, FILTER_VALIDATE_INT, ['options'=>['min_range'=>1,'max_range'=>100000]]);
            if ($capacity === false) { throw new InvalidArgumentException('Capacity must be a whole number from 1 to 100000.'); }
            if ($this->registered($id) > $capacity) { throw new InvalidArgumentException('Capacity cannot be below existing registrations.'); }
            $fee = trim((string)($input['fee'] ?? '0')); $feeCents = $fee === '' ? 0 : self::cents($fee);
            if ($feeCents !== 0 && $feeCents < 50) { throw new InvalidArgumentException('Entry fee must be $0 for a free event, or at least $0.50.'); }
            $this->store->put('event', $id, ['id'=>$id,'name'=>self::text($input['name'] ?? '', 'event name'),'date'=>self::date($input['date'] ?? ''),'capacity'=>$capacity,'fee_cents'=>$feeCents]);
        });
    }
    private static function registrationKey(string $event, string $member): string { return hash('sha256', "$event:$member"); }
    /** Pending and confirmed places count against capacity. Released and refunded places do not. */
    private static function holdsPlace(array $registration): bool { return !in_array($registration['status'] ?? 'confirmed', ['released','refunded'], true); }
    private function registered(string $event): int {
        return count(array_filter($this->store->all('registration'), fn($r)=>$r['event'] === $event && self::holdsPlace($r)));
    }
    public function register(string $eventId, string $memberId): void {
        $this->store->atomic(function() use ($eventId, $memberId) {
            $event = $this->requireRecord('event', $eventId); $this->requireRecord('member', $memberId); $key = self::registrationKey($eventId, $memberId);
            if (($event['fee_cents'] ?? 0) > 0) { throw new InvalidArgumentException('This event has an entry fee. Create a card payment link instead.'); }
            if ($old = $this->store->get('registration', $key)) { if (self::holdsPlace($old)) { return; } }
            if ($this->registered($eventId) >= $event['capacity']) { throw new InvalidArgumentException('Event is full.'); }
            $this->store->put('registration', $key, ['id'=>$key,'event'=>$eventId,'member'=>$memberId,'date'=>$this->today,'status'=>'confirmed']);
        });
    }
    public function saveSponsor(array $input): void { $this->store->atomic(function() use ($input) { $this->writeSponsor($input); }); }
    private function writeSponsor(array $input): void {
        $id = self::id($input['id'] ?? ''); $event = $this->requireRecord('event', (string)($input['event'] ?? ''));
        $amount = self::cents((string)($input['amount'] ?? '')); $paid = self::cents((string)($input['paid'] ?? ''));
        if ($paid > $amount) { throw new InvalidArgumentException('Paid amount cannot exceed the sponsorship agreement.'); }
        $this->store->put('sponsor', $id, ['id'=>$id,'name'=>self::text($input['name'] ?? '', 'sponsor name'),'event'=>$event['id'],'cents'=>$amount,'paid_cents'=>$paid,'agreement'=>self::text($input['agreement'] ?? '', 'agreement', 2000)]);
    }

    // Card payments. Stripe is called between beginPayment and attachSession, so
    // this class only stores state; StripeGateway and Checkout own the network calls.

    /** Creates a pending payment and holds the place before Stripe is called. */
    public function beginPayment(string $kind, string $memberId, ?string $eventId, string $amount): array {
        return $this->store->atomic(function() use ($kind, $memberId, $eventId, $amount) {
            $member = $this->requireRecord('member', $memberId); $id = bin2hex(random_bytes(12));
            if ($kind === 'registration') {
                $event = $this->requireRecord('event', (string)$eventId);
                $cents = (int)($event['fee_cents'] ?? 0);
                if ($cents < 50) { throw new InvalidArgumentException('This event has no entry fee. Register the member directly.'); }
                $key = self::registrationKey($event['id'], $member['id']);
                if ($old = $this->store->get('registration', $key)) {
                    if (self::holdsPlace($old)) { throw new InvalidArgumentException($old['status'] === 'confirmed' ? 'This member already has a place at this event.' : 'A card payment for this place is already open.'); }
                }
                if ($this->registered($event['id']) >= $event['capacity']) { throw new InvalidArgumentException('Event is full.'); }
                $this->store->put('registration', $key, ['id'=>$key,'event'=>$event['id'],'member'=>$member['id'],'date'=>$this->today,'status'=>'pending_payment','payment'=>$id]);
                $label = 'Event place: '.$event['name'];
            } elseif ($kind === 'renewal') {
                $cents = self::cents($amount);
                if ($cents < 50) { throw new InvalidArgumentException('A card payment must be at least $0.50.'); }
                $eventId = null; $label = 'Membership renewal';
            } else { throw new InvalidArgumentException('Unknown payment type.'); }
            $payment = ['id'=>$id,'kind'=>$kind,'member'=>$member['id'],'event'=>$eventId ? self::id($eventId) : null,'label'=>$label,'cents'=>$cents,'currency'=>'cad','status'=>'pending','session'=>null,'url'=>null,'payment_intent'=>null,'refunded_cents'=>0,'date'=>$this->today];
            $this->store->put('payment', $id, $payment);
            return $payment;
        });
    }
    public function attachSession(string $paymentId, string $sessionId, string $url): void {
        $this->store->atomic(function() use ($paymentId, $sessionId, $url) {
            $payment = $this->requirePayment($paymentId);
            $payment['session'] = $sessionId; $payment['url'] = $url;
            // A fast webhook may already have moved the payment on; keep that status.
            if ($payment['status'] === 'pending') { $payment['status'] = 'open'; }
            $this->store->put('payment', $paymentId, $payment);
        });
    }
    /** Releases the hold when Stripe refused to create the session. */
    public function cancelPayment(string $paymentId): void {
        $this->store->atomic(function() use ($paymentId) {
            $payment = $this->requirePayment($paymentId);
            if (!in_array($payment['status'], ['pending','open'], true)) { return; }
            $this->closePayment($payment, 'failed');
        });
    }
    private function requirePayment(string $id): array {
        return $this->store->get('payment', self::id($id)) ?? throw new InvalidArgumentException('Unknown payment.');
    }
    /**
     * Applies a signed Checkout Session event. Every branch is idempotent: a repeated
     * or late webhook finds the payment in a final state and changes nothing.
     */
    public function applyCheckoutSession(string $type, array $session): bool {
        return $this->store->atomic(function() use ($type, $session) {
            $paymentId = (string)($session['metadata']['payment_id'] ?? '');
            if (!preg_match('/^[a-f0-9]{24}$/D', $paymentId)) { return false; }
            $payment = $this->store->get('payment', $paymentId);
            if (!$payment) { return false; }
            if ($payment['session'] !== null && $payment['session'] !== ($session['id'] ?? null)) { throw new InvalidArgumentException('Checkout session does not match its payment.'); }
            if (in_array($payment['status'], ['paid','refunded','review','expired','failed'], true)) { return true; }
            if (in_array($type, ['checkout.session.completed','checkout.session.async_payment_succeeded'], true)) {
                if (($session['payment_status'] ?? '') !== 'paid') { $payment['status'] = 'processing'; $this->store->put('payment', $paymentId, $payment); return true; }
                $payment['payment_intent'] = is_string($session['payment_intent'] ?? null) ? $session['payment_intent'] : null;
                if (($session['amount_total'] ?? null) !== $payment['cents'] || ($session['currency'] ?? '') !== 'cad') {
                    $payment['status'] = 'review'; $this->store->put('payment', $paymentId, $payment); return true;
                }
                if ($payment['kind'] === 'registration') {
                    if (!$this->confirmPlace($payment)) { $payment['status'] = 'review'; $this->store->put('payment', $paymentId, $payment); return true; }
                } else {
                    // Receipt ID is derived from the payment, so a replayed webhook extends the membership once.
                    $this->recordRenewal($payment['member'], 'stripe-'.$paymentId, $payment['cents'], 'stripe');
                }
                $payment['status'] = 'paid'; $this->store->put('payment', $paymentId, $payment);
                return true;
            }
            if (in_array($type, ['checkout.session.expired','checkout.session.async_payment_failed'], true)) {
                $this->closePayment($payment, $type === 'checkout.session.expired' ? 'expired' : 'failed');
                return true;
            }
            return true;
        });
    }
    private function closePayment(array $payment, string $status): void {
        $payment['status'] = $status; $this->store->put('payment', $payment['id'], $payment);
        if ($payment['kind'] !== 'registration') { return; }
        $key = self::registrationKey($payment['event'], $payment['member']); $place = $this->store->get('registration', $key);
        if ($place && ($place['payment'] ?? null) === $payment['id'] && $place['status'] === 'pending_payment') {
            $place['status'] = 'released'; $this->store->put('registration', $key, $place);
        }
    }
    private function confirmPlace(array $payment): bool {
        $key = self::registrationKey($payment['event'], $payment['member']); $place = $this->store->get('registration', $key);
        if (!$place || ($place['payment'] ?? null) !== $payment['id'] || $place['status'] !== 'pending_payment') { return false; }
        $place['status'] = 'confirmed'; $this->store->put('registration', $key, $place);
        return true;
    }
    /** Charge refunds carry cumulative amount_refunded, so applying the same event twice changes nothing. */
    public function applyRefund(array $charge): bool {
        return $this->store->atomic(function() use ($charge) {
            $intent = (string)($charge['payment_intent'] ?? '');
            if (!preg_match('/^pi_[A-Za-z0-9_]+$/D', $intent)) { return false; }
            $payment = null;
            foreach ($this->store->all('payment') as $candidate) { if (($candidate['payment_intent'] ?? null) === $intent) { $payment = $candidate; break; } }
            if (!$payment) { return false; }
            $refunded = (int)($charge['amount_refunded'] ?? 0);
            if ($refunded < 0 || $refunded > $payment['cents']) { throw new InvalidArgumentException('Refund amount is outside the payment.'); }
            $payment['refunded_cents'] = $refunded;
            if ($refunded === $payment['cents']) {
                $payment['status'] = 'refunded';
                if ($payment['kind'] === 'registration') {
                    $key = self::registrationKey($payment['event'], $payment['member']); $place = $this->store->get('registration', $key);
                    if ($place && ($place['payment'] ?? null) === $payment['id']) { $place['status'] = 'refunded'; $this->store->put('registration', $key, $place); }
                }
            }
            if ($payment['kind'] === 'renewal' && ($renewal = $this->store->get('renewal', 'stripe-'.$payment['id']))) {
                $renewal['refunded_cents'] = $refunded; $this->store->put('renewal', $renewal['id'], $renewal);
            }
            $this->store->put('payment', $payment['id'], $payment);
            return true;
        });
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
        $registrations = $this->store->all('registration'); $payments = $this->store->all('payment');
        $pledged = array_sum(array_column($sponsors, 'cents')); $paid = array_sum(array_column($sponsors, 'paid_cents'));
        $netRenewals = array_sum(array_map(fn($r)=>$r['cents'] - ($r['refunded_cents'] ?? 0), $renewals));
        $eventFees = array_sum(array_map(fn($p)=>$p['cents'] - $p['refunded_cents'], array_filter($payments, fn($p)=>$p['kind'] === 'registration' && $p['status'] === 'paid')));
        return ['members'=>count($members),'active'=>count(array_filter($members, fn($m)=>$m['expires'] >= $this->today)),
            'due'=>count(array_filter($members, fn($m)=>$m['expires'] >= $this->today && $m['expires'] <= (new \DateTimeImmutable($this->today))->modify('+30 days')->format('Y-m-d'))),
            'renewals'=>count($renewals),'renewed_members'=>count(array_unique(array_column($renewals, 'member'))),'renewal_cents'=>$netRenewals,
            'registrations'=>count(array_filter($registrations, fn($r)=>self::holdsPlace($r))),'event_fees_cents'=>$eventFees,
            'sponsor_cents'=>$pledged,'sponsor_paid_cents'=>$paid,'sponsor_outstanding_cents'=>$pledged-$paid,
            'sent'=>count(array_filter($deliveries,fn($d)=>$d['status'] === 'sent')),'opened'=>count(array_filter($deliveries,fn($d)=>$d['opened'])),
            'failed'=>count(array_filter($deliveries,fn($d)=>$d['status'] === 'failed'))];
    }
}
