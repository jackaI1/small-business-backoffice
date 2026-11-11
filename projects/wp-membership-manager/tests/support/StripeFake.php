<?php
/**
 * Mocked Stripe API transport. StripeGateway builds real requests and verifies real
 * signatures; only the network call is replaced, so tests never reach api.stripe.com.
 */
final class StripeFake {
    /** @var list<array{method:string,url:string,headers:array<string,string>,body:string}> */
    public array $requests = [];
    public int $status = 200;
    public ?string $body = null;

    public function __invoke(string $method, string $url, array $headers, string $body): array {
        $this->requests[] = ['method'=>$method, 'url'=>$url, 'headers'=>$headers, 'body'=>$body];
        $n = count($this->requests);
        return ['status'=>$this->status, 'body'=>$this->body ?? json_encode(['id'=>"cs_test_$n", 'object'=>'checkout.session', 'url'=>"https://checkout.stripe.test/c/$n"], JSON_THROW_ON_ERROR)];
    }
    /** Builds a Stripe-Signature header exactly as Stripe does: t=<unix>,v1=<HMAC-SHA256 of "<t>.<payload>">. */
    public static function signature(string $payload, string $secret, int $timestamp): string {
        return "t=$timestamp,v1=".hash_hmac('sha256', "$timestamp.$payload", $secret);
    }
    /** Loads a signed-payload fixture and fills its {{placeholders}}. */
    public static function fixture(string $name, array $values): string {
        $json = file_get_contents(__DIR__.'/../fixtures/stripe/'.$name.'.json');
        foreach ($values as $key => $value) { $json = str_replace('{{'.$key.'}}', (string)$value, $json); }
        return $json;
    }
}
