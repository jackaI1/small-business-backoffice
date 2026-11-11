<?php
use PHPUnit\Framework\TestCase;
use WPMM\Checkout;
use WPMM\Manager;
use WPMM\StripeGateway;
require_once __DIR__.'/../support/MemoryStore.php';
require_once __DIR__.'/../support/StripeFake.php';

final class CheckoutTest extends TestCase {
    private const SECRET = 'whsec_test_example';
    private MemoryStore $store;
    private Manager $app;
    private StripeFake $stripe;
    private Checkout $checkout;

    protected function setUp(): void {
        $this->store = new MemoryStore();
        $this->app = new Manager($this->store, '2026-06-01');
        $this->stripe = new StripeFake();
        $this->checkout = new Checkout($this->app, new StripeGateway('sk_test_example', self::SECRET, $this->stripe), 'https://club.example.test/');
        $this->app->saveMember(['id'=>'m1','name'=>'Alex Example','email'=>'m1@example.test','level'=>'student','expires'=>'2026-06-20','consent'=>true]);
        $this->app->saveMember(['id'=>'m2','name'=>'Morgan Example','email'=>'m2@example.test','level'=>'student','expires'=>'2026-06-20','consent'=>true]);
        $this->app->saveEvent(['id'=>'e1','name'=>'Research Night','date'=>'2026-07-01','capacity'=>1,'fee'=>'25.00']);
    }
    private function paymentId(): string { return array_values($this->store->rows['payment'])[0]['id']; }
    private function payment(string $id): array { return $this->store->rows['payment'][$id]; }
    /** Sends a Stripe-signed webhook through the same entry point the WordPress endpoint uses. */
    private function webhook(string $fixture, array $values, ?string $secret = null, ?int $timestamp = null): int {
        $payload = StripeFake::fixture($fixture, $values);
        $timestamp ??= time();
        return $this->checkout->handleWebhook($payload, StripeFake::signature($payload, $secret ?? self::SECRET, $timestamp));
    }
    private function completed(string $paymentId, string $sessionId, int $amount = 2500, string $status = 'paid'): int {
        return $this->webhook('checkout-session-completed', ['payment_id'=>$paymentId,'session_id'=>$sessionId,'amount'=>$amount,'payment_status'=>$status,'payment_intent'=>'pi_test_1']);
    }
    private function refunded(int $amountRefunded, int $amount = 2500): int {
        return $this->webhook('charge-refunded', ['payment_intent'=>'pi_test_1','amount'=>$amount,'amount_refunded'=>$amountRefunded,'fully_refunded'=>$amountRefunded === $amount ? 'true' : 'false']);
    }
    private function place(string $member = 'm1'): ?array { return $this->store->rows['registration'][hash('sha256', "e1:$member")] ?? null; }

    public function testCheckoutSessionIsCreatedWithServerSideAmountAndHoldsThePlace(): void {
        $url = $this->checkout->registrationLink('e1', 'm1');
        self::assertSame('https://checkout.stripe.test/c/1', $url);
        $request = $this->stripe->requests[0];
        self::assertSame('POST', $request['method']);
        self::assertSame('https://api.stripe.com/v1/checkout/sessions', $request['url']);
        self::assertSame('Bearer sk_test_example', $request['headers']['Authorization']);
        self::assertStringStartsWith('wpmm-', $request['headers']['Idempotency-Key']);
        // Amount comes from the stored event fee, never from the browser or the form.
        self::assertStringContainsString('line_items[0][price_data][unit_amount]=2500', $request['body']);
        self::assertStringContainsString('line_items[0][price_data][currency]=cad', $request['body']);
        self::assertStringContainsString('metadata[payment_id]='.$this->paymentId(), $request['body']);
        self::assertSame('open', $this->payment($this->paymentId())['status']);
        self::assertSame('pending_payment', $this->place()['status']);
    }
    public function testPaidPlaceIsConfirmedOnlyByWebhookAndRepeatsChangeNothing(): void {
        $this->checkout->registrationLink('e1', 'm1');
        $id = $this->paymentId();
        self::assertSame(200, $this->completed($id, 'cs_test_1'));
        self::assertSame('confirmed', $this->place()['status']);
        self::assertSame('paid', $this->payment($id)['status']);
        self::assertSame(200, $this->completed($id, 'cs_test_1'));
        self::assertSame(1, $this->app->report()['registrations']);
        self::assertSame(2500, $this->app->report()['event_fees_cents']);
    }
    public function testSeatIsHeldWhilePendingSoASecondMemberCannotOverbook(): void {
        $this->checkout->registrationLink('e1', 'm1');
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('Event is full.');
        $this->checkout->registrationLink('e1', 'm2');
    }
    public function testExpiredCheckoutReleasesThePlace(): void {
        $this->checkout->registrationLink('e1', 'm1');
        self::assertSame(200, $this->webhook('checkout-session-expired', ['payment_id'=>$this->paymentId(),'session_id'=>'cs_test_1','amount'=>2500]));
        self::assertSame('released', $this->place()['status']);
        self::assertSame('expired', $this->payment($this->paymentId())['status']);
        self::assertSame(0, $this->app->report()['registrations']);
        // The freed place can be offered to the next member.
        self::assertSame('https://checkout.stripe.test/c/2', $this->checkout->registrationLink('e1', 'm2'));
    }
    public function testDelayedBankPaymentStaysProcessingThenSucceeds(): void {
        $this->checkout->registrationLink('e1', 'm1'); $id = $this->paymentId();
        $this->completed($id, 'cs_test_1', 2500, 'unpaid');
        self::assertSame('processing', $this->payment($id)['status']);
        self::assertSame('pending_payment', $this->place()['status']);
        self::assertSame(200, $this->webhook('checkout-session-completed', ['payment_id'=>$id,'session_id'=>'cs_test_1','amount'=>2500,'payment_status'=>'paid','payment_intent'=>'pi_test_1']));
        self::assertSame('confirmed', $this->place()['status']);
    }
    public function testFailedDelayedPaymentReleasesThePlace(): void {
        $this->checkout->registrationLink('e1', 'm1'); $id = $this->paymentId();
        $this->completed($id, 'cs_test_1', 2500, 'unpaid');
        self::assertSame(200, $this->webhook('checkout-session-expired', ['payment_id'=>$id,'session_id'=>'cs_test_1','amount'=>2500]));
        self::assertSame('released', $this->place()['status']);
    }
    public function testAmountMismatchIsSentToReviewAndNotConfirmed(): void {
        $this->checkout->registrationLink('e1', 'm1'); $id = $this->paymentId();
        self::assertSame(200, $this->completed($id, 'cs_test_1', 1000));
        self::assertSame('review', $this->payment($id)['status']);
        self::assertSame('pending_payment', $this->place()['status']);
    }
    public function testPaidRenewalExtendsOnceThroughTheReceiptLedger(): void {
        $this->checkout->renewalLink('m1', '25.00'); $id = $this->paymentId();
        for ($i = 0; $i < 3; $i++) { self::assertSame(200, $this->completed($id, 'cs_test_1')); }
        self::assertSame('2027-06-20', $this->store->rows['member']['m1']['expires']);
        self::assertSame(1, $this->app->report()['renewals']);
        self::assertSame(2500, $this->app->report()['renewal_cents']);
        self::assertSame('stripe', $this->store->rows['renewal']['stripe-'.$id]['source']);
    }
    public function testRenewalRefundIsRecordedAndNetOfTheReport(): void {
        $this->checkout->renewalLink('m1', '25.00'); $id = $this->paymentId();
        $this->completed($id, 'cs_test_1');
        self::assertSame(200, $this->refunded(1000));
        self::assertSame('paid', $this->payment($id)['status']);
        self::assertSame(1000, $this->payment($id)['refunded_cents']);
        self::assertSame(1500, $this->app->report()['renewal_cents']);
        self::assertSame(200, $this->refunded(2500));
        self::assertSame('refunded', $this->payment($id)['status']);
        self::assertSame(0, $this->app->report()['renewal_cents']);
        self::assertSame(200, $this->refunded(2500)); // Replayed charge event changes nothing.
        self::assertSame(0, $this->app->report()['renewal_cents']);
        // The membership date is not shortened automatically; the administrator decides.
        self::assertSame('2027-06-20', $this->store->rows['member']['m1']['expires']);
    }
    public function testFullRefundFreesThePlace(): void {
        $this->checkout->registrationLink('e1', 'm1'); $id = $this->paymentId();
        $this->completed($id, 'cs_test_1');
        self::assertSame(200, $this->refunded(2500));
        self::assertSame('refunded', $this->place()['status']);
        self::assertSame('refunded', $this->payment($id)['status']);
        self::assertSame(0, $this->app->report()['event_fees_cents']);
        self::assertSame('https://checkout.stripe.test/c/2', $this->checkout->registrationLink('e1', 'm2'));
    }
    public function testBadSignatureTamperingAndOldTimestampAreRejectedWithoutChanges(): void {
        $this->checkout->registrationLink('e1', 'm1'); $id = $this->paymentId();
        $payload = StripeFake::fixture('checkout-session-completed', ['payment_id'=>$id,'session_id'=>'cs_test_1','amount'=>2500,'payment_status'=>'paid','payment_intent'=>'pi_test_1']);
        self::assertSame(400, $this->checkout->handleWebhook($payload, StripeFake::signature($payload, 'whsec_wrong', time())));
        $tampered = str_replace('"amount_total": 2500', '"amount_total": 1', $payload);
        self::assertSame(400, $this->checkout->handleWebhook($tampered, StripeFake::signature($payload, self::SECRET, time())));
        self::assertSame(400, $this->checkout->handleWebhook($payload, StripeFake::signature($payload, self::SECRET, time() - 3600)));
        self::assertSame(400, $this->checkout->handleWebhook($payload, ''));
        self::assertSame('pending_payment', $this->place()['status']);
        self::assertSame('open', $this->payment($id)['status']);
    }
    public function testWebhookForUnknownPaymentIsAcknowledgedAndIgnored(): void {
        self::assertSame(200, $this->completed('0123456789abcdef01234567', 'cs_test_x'));
        self::assertSame([], $this->store->rows['payment'] ?? []);
    }
    public function testSessionIdMustMatchThePaymentItBelongsTo(): void {
        $this->checkout->registrationLink('e1', 'm1');
        self::assertSame(400, $this->completed($this->paymentId(), 'cs_test_other'));
        self::assertSame('pending_payment', $this->place()['status']);
    }
    public function testStripeRefusalReleasesTheHoldAndShowsTheReason(): void {
        $this->stripe->status = 402;
        $this->stripe->body = json_encode(['error'=>['message'=>'Your account cannot accept payments.']]);
        try { $this->checkout->registrationLink('e1', 'm1'); self::fail('Refusal accepted'); }
        catch (InvalidArgumentException $e) { self::assertStringContainsString('cannot accept payments', $e->getMessage()); }
        self::assertSame('failed', $this->payment($this->paymentId())['status']);
        self::assertSame('released', $this->place()['status']);
        self::assertSame(0, $this->app->report()['registrations']);
    }
    public function testFreeEventsAndCardRenewalsHaveTheirOwnRules(): void {
        $this->app->saveEvent(['id'=>'free','name'=>'Open Lab','date'=>'2026-07-02','capacity'=>5,'fee'=>'0']);
        $requests = count($this->stripe->requests);
        try { $this->checkout->registrationLink('free', 'm1'); self::fail('Free event charged'); } catch (InvalidArgumentException $e) { self::assertStringContainsString('no entry fee', $e->getMessage()); }
        try { $this->app->register('e1', 'm1'); self::fail('Paid event registered without payment'); } catch (InvalidArgumentException $e) { self::assertStringContainsString('card payment link', $e->getMessage()); }
        $this->app->register('free', 'm1');
        self::assertSame('confirmed', $this->store->rows['registration'][hash('sha256', 'free:m1')]['status']);
        try { $this->checkout->renewalLink('m1', '0.40'); self::fail('Sub-minimum renewal accepted'); } catch (InvalidArgumentException $e) { self::assertStringContainsString('at least $0.50', $e->getMessage()); }
        self::assertCount($requests, $this->stripe->requests); // No Stripe call was made for rejected requests.
    }
    public function testEventFeeValidationRejectsSubMinimumAmounts(): void {
        $this->expectException(InvalidArgumentException::class);
        $this->app->saveEvent(['id'=>'e9','name'=>'Tiny','date'=>'2026-07-02','capacity'=>5,'fee'=>'0.40']);
    }
}
