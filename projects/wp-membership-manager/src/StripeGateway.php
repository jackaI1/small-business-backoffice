<?php
namespace WPMM;

use InvalidArgumentException;
use RuntimeException;

/**
 * Minimal Stripe client. It uses an injected HTTP function so WordPress supplies
 * wp_remote_request in production and tests supply a fake. No SDK is needed at runtime.
 */
final class StripeGateway implements CheckoutGateway {
    private const API = 'https://api.stripe.com/v1';
    private const TOLERANCE_SECONDS = 300;

    /** @var callable(string,string,array<string,string>,string):array{status:int,body:string} */
    private $http;

    public function __construct(private string $secretKey, private string $webhookSecret, callable $http) {
        // Refuse live keys so this learning project cannot charge real cards by accident.
        // An empty key is allowed: webhook verification needs only the webhook secret.
        if ($secretKey !== '' && !str_starts_with($secretKey, 'sk_test_')) { throw new InvalidArgumentException('Use a Stripe test secret key (sk_test_...) in WPMM_STRIPE_SECRET_KEY.'); }
        $this->http = $http;
    }

    public function createCheckoutSession(array $params, string $idempotencyKey): array {
        if ($this->secretKey === '') { throw new InvalidArgumentException('Set WPMM_STRIPE_SECRET_KEY to a Stripe test key (sk_test_...).'); }
        $response = ($this->http)('POST', self::API.'/checkout/sessions', [
            'Authorization' => 'Bearer '.$this->secretKey,
            'Content-Type' => 'application/x-www-form-urlencoded',
            'Idempotency-Key' => 'wpmm-'.$idempotencyKey,
        ], self::formBody(self::flatten($params)));
        $data = json_decode($response['body'], true);
        if ($response['status'] < 200 || $response['status'] >= 300 || !is_array($data) || !is_string($data['id'] ?? null) || !is_string($data['url'] ?? null)) {
            $message = is_array($data) ? substr((string)($data['error']['message'] ?? 'unexpected response'), 0, 200) : 'unexpected response';
            throw new RuntimeException("Stripe rejected the checkout: $message");
        }
        return ['id'=>$data['id'], 'url'=>$data['url']];
    }

    /** Stripe's documented scheme: HMAC-SHA256 over "timestamp.payload", with a five-minute tolerance. */
    public function verifyEvent(string $payload, string $signature, ?int $now = null): array {
        if ($this->webhookSecret === '') { throw new RuntimeException('Stripe webhook secret is not configured.'); }
        $timestamp = null; $signatures = [];
        foreach (explode(',', $signature) as $part) {
            [$key, $value] = array_pad(explode('=', trim($part), 2), 2, '');
            if ($key === 't' && ctype_digit($value)) { $timestamp = (int)$value; }
            if ($key === 'v1') { $signatures[] = $value; }
        }
        if ($timestamp === null || !$signatures || abs(($now ?? time()) - $timestamp) > self::TOLERANCE_SECONDS) {
            throw new InvalidArgumentException('Invalid Stripe signature.');
        }
        $expected = hash_hmac('sha256', $timestamp.'.'.$payload, $this->webhookSecret);
        $valid = false;
        foreach ($signatures as $candidate) { $valid = hash_equals($expected, $candidate) || $valid; }
        if (!$valid) { throw new InvalidArgumentException('Invalid Stripe signature.'); }
        $event = json_decode($payload, true);
        if (!is_array($event) || !is_string($event['type'] ?? null) || !is_array($event['data']['object'] ?? null)) {
            throw new InvalidArgumentException('Stripe event is malformed.');
        }
        // A test-mode site never applies a live-mode event, even one Stripe signed.
        if (($event['livemode'] ?? false) !== false) { throw new InvalidArgumentException('Live-mode events are refused in test mode.'); }
        return $event;
    }

    /** Form body with raw bracket names, as in Stripe's own examples; only values are percent-encoded. */
    private static function formBody(array $flat): string {
        return implode('&', array_map(fn($name, $value) => $name.'='.rawurlencode($value), array_keys($flat), $flat));
    }

    /** Turns nested arrays into Stripe's bracket names, for example line_items[0][quantity]. */
    private static function flatten(array $params, string $prefix = ''): array {
        $flat = [];
        foreach ($params as $key => $value) {
            $name = $prefix === '' ? (string)$key : $prefix.'['.$key.']';
            if (is_array($value)) { $flat += self::flatten($value, $name); }
            else { $flat[$name] = (string)$value; }
        }
        return $flat;
    }
}
