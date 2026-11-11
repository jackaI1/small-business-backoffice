<?php
namespace WPMM;

/** The only place card payments leave the plugin. Tests replace it with a fake. */
interface CheckoutGateway {
    /** @return array{id: string, url: string} */
    public function createCheckoutSession(array $params, string $idempotencyKey): array;
    /**
     * Checks the Stripe-Signature header and returns the verified event.
     * @throws \InvalidArgumentException when the signature or event shape is wrong.
     */
    public function verifyEvent(string $payload, string $signature): array;
}
