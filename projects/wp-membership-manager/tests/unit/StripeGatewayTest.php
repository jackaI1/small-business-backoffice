<?php
use PHPUnit\Framework\TestCase;
use WPMM\StripeGateway;
require_once __DIR__.'/../support/StripeFake.php';

final class StripeGatewayTest extends TestCase {
    private const SECRET = 'whsec_test_example';
    private const NOW = 1780000000;

    private function gateway(string $secret = self::SECRET): StripeGateway {
        return new StripeGateway('sk_test_example', $secret, new StripeFake());
    }
    private function signedFixture(string $name = 'checkout-session-completed', string $secret = self::SECRET): array {
        $payload = StripeFake::fixture($name, ['payment_id'=>'0123456789abcdef01234567','session_id'=>'cs_test_1','amount'=>2500,'payment_status'=>'paid','payment_intent'=>'pi_test_1','fully_refunded'=>'false','amount_refunded'=>0]);
        return [$payload, StripeFake::signature($payload, $secret, self::NOW)];
    }
    public function testSignedFixtureVerifiesAndParsesToTheCheckoutSession(): void {
        [$payload, $header] = $this->signedFixture();
        $event = $this->gateway()->verifyEvent($payload, $header, self::NOW + 5);
        self::assertSame('checkout.session.completed', $event['type']);
        self::assertSame(2500, $event['data']['object']['amount_total']);
        self::assertSame('0123456789abcdef01234567', $event['data']['object']['metadata']['payment_id']);
    }
    public function testSignatureFromAnotherSecretIsRejected(): void {
        [$payload, $header] = $this->signedFixture('checkout-session-completed', 'whsec_someone_else');
        $this->expectException(InvalidArgumentException::class);
        $this->gateway()->verifyEvent($payload, $header, self::NOW);
    }
    public function testAnyMatchingSignatureDuringSecretRotationIsAccepted(): void {
        [$payload, $header] = $this->signedFixture();
        $current = substr($header, strpos($header, 'v1=') + 3);
        $rotated = 't='.self::NOW.',v1=deadbeef,v1='.$current.',v1=00';
        self::assertSame('checkout.session.completed', $this->gateway()->verifyEvent($payload, $rotated, self::NOW)['type']);
    }
    public function testTimestampToleranceIsFiveMinutes(): void {
        [$payload, $header] = $this->signedFixture();
        self::assertSame('checkout.session.completed', $this->gateway()->verifyEvent($payload, $header, self::NOW + 300)['type']);
        $this->expectException(InvalidArgumentException::class);
        $this->gateway()->verifyEvent($payload, $header, self::NOW + 301);
    }
    public function testAlteredPayloadFailsEvenWithAValidHeaderForTheOriginal(): void {
        [$payload, $header] = $this->signedFixture();
        $this->expectException(InvalidArgumentException::class);
        $this->gateway()->verifyEvent(str_replace('"amount_total": 2500', '"amount_total": 1', $payload), $header, self::NOW);
    }
    public function testSignedButMalformedEventIsRejected(): void {
        $payload = '{"type":"checkout.session.completed"}';
        $header = StripeFake::signature($payload, self::SECRET, self::NOW);
        $this->expectException(InvalidArgumentException::class);
        $this->gateway()->verifyEvent($payload, $header, self::NOW);
    }
    public function testMissingWebhookSecretIsAServerConfigurationErrorNotAForgery(): void {
        $this->expectException(RuntimeException::class);
        $this->gateway('')->verifyEvent('{}', 't=1,v1=x', self::NOW);
    }
    public function testLiveKeysAreRefusedSoTheDemoCannotChargeRealCards(): void {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('test secret key');
        new StripeGateway('sk_live_example', self::SECRET, new StripeFake());
    }
    public function testCheckoutRequestUsesFormBodyWithRawBracketNames(): void {
        $http = new StripeFake();
        $gateway = new StripeGateway('sk_test_example', self::SECRET, $http);
        $session = $gateway->createCheckoutSession(['mode'=>'payment','line_items'=>[['quantity'=>1,'price_data'=>['currency'=>'cad','unit_amount'=>2500,'product_data'=>['name'=>'Event place: Research & Night']]]]], 'abc');
        self::assertSame('cs_test_1', $session['id']);
        self::assertSame('wpmm-abc', $http->requests[0]['headers']['Idempotency-Key']);
        self::assertStringContainsString('line_items[0][price_data][product_data][name]=Event%20place%3A%20Research%20%26%20Night', $http->requests[0]['body']);
    }
    public function testStripeErrorBodyIsSummarisedWithoutLeakingTheWholeResponse(): void {
        $http = new StripeFake(); $http->status = 400; $http->body = json_encode(['error'=>['message'=>'Missing required param: expires_at.']]);
        $gateway = new StripeGateway('sk_test_example', self::SECRET, $http);
        $this->expectException(RuntimeException::class);
        $this->expectExceptionMessage('Missing required param');
        $gateway->createCheckoutSession(['mode'=>'payment'], 'abc');
    }
}
