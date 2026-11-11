<?php
use PHPUnit\Framework\TestCase;
use WPMM\Manager;
use WPMM\Store;
require_once __DIR__.'/../support/MemoryStore.php';

final class ManagerTest extends TestCase {
    private MemoryStore $store;
    private Manager $app;
    protected function setUp(): void { $this->store = new MemoryStore(); $this->app = new Manager($this->store, '2026-06-01'); }
    private function member(string $id = 'm1', array $changes = []): void {
        $this->app->saveMember(array_replace(['id'=>$id,'name'=>'Alex Example','email'=>$id.'@example.test','level'=>'student','expires'=>'2026-06-20','consent'=>true], $changes));
    }
    private function event(): void { $this->app->saveEvent(['id'=>'e1','name'=>'Research Night','date'=>'2026-07-01','capacity'=>2]); }
    private function campaign(string $segment = 'due'): string { return $this->app->createCampaign('Renewal reminder', '<p>Hello {{name}}</p>', $segment); }
    public function testSummaryCsvContainsTotalsWithoutPersonalDetails(): void {
        $this->member(); $this->app->renew('m1', 'r1', '25.50');
        $csv = $this->app->reportCsv();
        self::assertStringContainsString("members,1,count", $csv);
        self::assertStringContainsString('renewal,25.50,CAD', $csv);
        self::assertStringNotContainsString('m1@example.test', $csv);
        self::assertStringNotContainsString('Alex Example', $csv);
    }
    public function testSegmentsRespectConsentAndDateBoundaries(): void {
        $this->member(); $this->member('m2',['expires'=>'2026-05-31']); $this->member('m3',['expires'=>'2026-07-02']);
        $this->member('m4',['consent'=>false]); $this->member('m5',['expires'=>'2026-06-01']);
        self::assertCount(2,$this->app->segment('due')); self::assertCount(3,$this->app->segment('active'));
        self::assertCount(1,$this->app->segment('expired')); self::assertCount(4,$this->app->segment('all'));
    }
    public function testRejectsImpossibleDate(): void { $this->expectException(InvalidArgumentException::class); $this->member('m1',['expires'=>'2026-02-30']); }
    public function testRejectsInvalidEmail(): void { $this->expectException(InvalidArgumentException::class); $this->member('m1',['email'=>'bad']); }
    public function testRejectsDuplicateEmailAcrossIds(): void { $this->member(); $this->expectException(InvalidArgumentException::class); $this->member('m2',['email'=>'M1@example.test']); }
    public function testRenewalExtendsExpiryAndIsIdempotent(): void {
        $this->member(); $this->app->renew('m1','receipt1','25.50'); $this->app->renew('m1','receipt1','25.50');
        self::assertSame('2027-06-20',$this->store->get('member','m1')['expires']);
        self::assertSame(2550,$this->app->report()['renewal_cents']); self::assertSame(1,$this->app->report()['renewals']);
    }
    public function testExpiredRenewalStartsToday(): void { $this->member('m1',['expires'=>'2025-01-01']); $this->app->renew('m1','r1','10'); self::assertSame('2027-06-01',$this->store->get('member','m1')['expires']); }
    public function testReceiptCannotBeReusedWithDifferentAmount(): void { $this->member(); $this->app->renew('m1','r1','10'); $this->expectException(InvalidArgumentException::class); $this->app->renew('m1','r1','20'); }
    public function testMoneyRejectsNegativeFractionalAndExponentInputs(): void {
        foreach (['-1','1.001','1e3','NaN','1,000','999999999999'] as $amount) {
            try { Manager::cents($amount); self::fail('Accepted '.$amount); } catch (InvalidArgumentException) { self::assertTrue(true); }
        }
        self::assertSame(1234,Manager::cents('12.34'));
    }
    public function testRegistrationCapacityAndDuplicateAreEnforced(): void {
        $this->event(); $this->member(); $this->member('m2'); $this->member('m3');
        $this->app->register('e1','m1'); $this->app->register('e1','m1'); $this->app->register('e1','m2');
        self::assertSame(2,$this->app->report()['registrations']);
        $this->expectException(InvalidArgumentException::class); $this->app->register('e1','m3');
    }
    public function testSponsorsReportPledgedPaidAndOutstandingSeparately(): void {
        $this->event(); $this->app->saveSponsor(['id'=>'s1','name'=>'Example Lab','event'=>'e1','amount'=>'1500','paid'=>'500','agreement'=>'Logo on programme']);
        self::assertSame(150000,$this->app->report()['sponsor_cents']); self::assertSame(50000,$this->app->report()['sponsor_paid_cents']);
        self::assertSame(100000,$this->app->report()['sponsor_outstanding_cents']);
    }
    public function testSponsorCannotOverpay(): void { $this->event(); $this->expectException(InvalidArgumentException::class); $this->app->saveSponsor(['id'=>'s1','name'=>'X','event'=>'e1','amount'=>'1','paid'=>'2','agreement'=>'Logo']); }
    public function testCampaignSendsHtmlPersonalizationAndDoesNotResend(): void {
        $this->member('m1',['name'=>'Alex <Example>']); $id=$this->campaign(); $messages=[];
        $sender=function($to,$subject,$html) use (&$messages) { $messages[]=[$to,$subject,$html]; return true; };
        $this->app->send($id,$sender,'http://localhost:8080'); $this->app->send($id,$sender,'http://localhost:8080');
        self::assertCount(1,$messages); self::assertStringContainsString('Alex &lt;Example&gt;',$messages[0][2]);
        self::assertStringContainsString('wpmm_open=',$messages[0][2]); self::assertStringContainsString('wpmm_unsubscribe=',$messages[0][2]);
        self::assertSame(1,$this->app->report()['sent']);
    }
    public function testFailedMailCanRetryAndConsentIsRechecked(): void {
        $this->member(); $id=$this->campaign(); $this->app->send($id,fn()=>false,'http://localhost');
        self::assertSame(1,$this->app->report()['failed']);
        $this->app->send($id,fn()=>true,'http://localhost'); self::assertSame(1,$this->app->report()['sent']);
        $id2=$this->campaign(); $this->member('m1',['consent'=>false]);
        $this->app->send($id2,function(){ self::fail('Sent to opted out member'); },'http://localhost');
        self::assertSame('skipped',$this->app->deliveries($id2)[0]['status']);
    }
    public function testOpenIsUniqueAndUnsubscribePersists(): void {
        $this->member(); $id=$this->campaign(); $token=$this->app->deliveries($id)[0]['token'];
        self::assertFalse($this->app->open($token)); $this->app->send($id,fn()=>true,'http://localhost');
        self::assertTrue($this->app->open($token)); self::assertTrue($this->app->open($token));
        self::assertSame(1,$this->app->report()['opened']); self::assertFalse($this->app->open(str_repeat('a',64)));
        self::assertTrue($this->app->unsubscribe($token)); self::assertCount(0,$this->app->segment('all'));
    }
    public function testCsvImportUpsertsAndFeedsReports(): void {
        $this->event(); $csv=file_get_contents(__DIR__.'/../../demo/salesforce-report.csv');
        self::assertSame(3,$this->app->importCsv($csv)); self::assertSame(3,$this->app->importCsv($csv));
        self::assertSame(2,$this->app->report()['members']); self::assertSame(150000,$this->app->report()['sponsor_cents']);
    }
    public function testMalformedCsvRollsBackEntireFile(): void {
        $csv="Record Type,Record ID,Name,Email,Level,Expires On,Email Consent,Event ID,Amount,Paid Amount,Agreement\nmember,m1,Alex,m1@example.test,student,2026-06-20,yes,,,,\nmember,m2,Bad,bad,student,2026-06-20,yes,,,,\n";
        try { $this->app->importCsv($csv); self::fail('Bad row accepted'); } catch (InvalidArgumentException) { self::assertSame(0,$this->app->report()['members']); }
    }
    public function testCsvRejectsMissingHeadersAndDuplicateIds(): void {
        foreach (["Email\na@example.test\n", "Record Type,Record ID,Name,Email,Level,Expires On,Email Consent,Event ID,Amount,Paid Amount,Agreement\nmember,m1,A,a@example.test,x,2026-06-01,yes,,,,\nmember,m1,B,b@example.test,x,2026-06-01,yes,,,,\n"] as $csv) {
            try { $this->app->importCsv($csv); self::fail('Invalid CSV accepted'); } catch (InvalidArgumentException) { self::assertSame(0,$this->app->report()['members']); }
        }
    }
    public function testReimportCannotUndoRenewalOrUnsubscribe(): void {
        $csv=file_get_contents(__DIR__.'/../../demo/salesforce-report.csv'); $this->event(); $this->app->importCsv($csv);
        $id=$this->app->createCampaign('Hello','<p>Hi</p>','all'); $token=$this->app->deliveries($id)[0]['token']; $this->app->unsubscribe($token);
        $this->app->renew('003-demo-1','r1','25'); $this->app->importCsv($csv);
        self::assertFalse($this->store->get('member','003-demo-1')['consent']); self::assertSame('2027-06-20',$this->store->get('member','003-demo-1')['expires']);
    }
    public function testSalesforceContactAndOpportunityExportsMapWithoutInventedColumns(): void {
        $this->event();
        $contacts = "Contact ID,Full Name,Email,Membership Level,Membership Expiry,Email Opt Out\n003-a,Alex Export,export@example.test,student,2026-06-20,false\n003-b,Sam Export,optout@example.test,professional,2026-07-20,true\n";
        self::assertSame(2,$this->app->importCsv($contacts));
        self::assertCount(1,$this->app->segment('all'));
        $sponsors = "Opportunity ID,Account Name,Event ID,Amount,Amount Paid,Agreement\n006-a,Export Lab,e1,2000.00,1250.00,Programme logo\n";
        self::assertSame(1,$this->app->importCsv($sponsors)); self::assertSame(200000,$this->app->report()['sponsor_cents']);
    }
    public function testCapacityCannotBeReducedBelowBookings(): void {
        $this->event(); $this->member(); $this->member('m2'); $this->app->register('e1','m1'); $this->app->register('e1','m2');
        $this->expectException(InvalidArgumentException::class); $this->app->saveEvent(['id'=>'e1','name'=>'Research Night','date'=>'2026-07-01','capacity'=>1]);
    }
    public function testUnknownEventCannotCreateSponsor(): void {
        $this->expectException(InvalidArgumentException::class); $this->app->saveSponsor(['id'=>'s1','name'=>'Example','event'=>'missing','amount'=>'100','paid'=>'0','agreement'=>'Logo']);
    }
    public function testSubjectRejectsHeaderInjection(): void {
        $this->member(); $this->expectException(InvalidArgumentException::class); $this->app->createCampaign("Hello\r\nBcc: x@example.test",'<p>Hello</p>','all');
    }
    public function testCsvAllowsBomQuotedCommasAndExtraColumns(): void {
        $csv = "\xEF\xBB\xBFRecord Type,Record ID,Name,Email,Level,Expires On,Email Consent,Event ID,Amount,Paid Amount,Agreement,Extra\nmember,m1,\"Example, Alex\",a@example.test,student,2026-06-20,yes,,,,,ignored\n";
        self::assertSame(1,$this->app->importCsv($csv)); self::assertSame('Example, Alex',$this->store->get('member','m1')['name']);
    }

    public function testPendingRecipientsAreNotStarvedByFailedRetries(): void {
        for ($i=0; $i<101; ++$i) { $this->member(sprintf('m%03d',$i)); }
        $id=$this->campaign(); $this->app->send($id,fn()=>false,'http://localhost');
        $attempted=[];
        $this->app->send($id,function($email) use (&$attempted) { $attempted[]=$email; return false; },'http://localhost');
        self::assertCount(100,$attempted); self::assertContains('m100@example.test',$attempted);
        self::assertCount(0,array_filter($this->app->deliveries($id),fn($d)=>$d['status'] === 'pending'));
    }

}
