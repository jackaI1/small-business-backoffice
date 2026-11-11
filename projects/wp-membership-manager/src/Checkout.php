<?php
namespace WPMM;

use InvalidArgumentException;
use RuntimeException;

/** Creates Stripe-hosted payment pages for the admin and applies signed webhooks. */
final class Checkout {
    public function __construct(private Manager $manager, private CheckoutGateway $gateway, private string $returnUrl) {}

    public function registrationLink(string $eventId, string $memberId): string {
        return $this->start('registration', $memberId, $eventId, '0');
    }
    public function renewalLink(string $memberId, string $amount): string {
        return $this->start('renewal', $memberId, null, $amount);
    }
    private function start(string $kind, string $memberId, ?string $eventId, string $amount): string {
        // The place or amount is held in the database before Stripe is called, so the
        // webhook always has a payment record to match. A failed Stripe call releases it.
        $payment = $this->manager->beginPayment($kind, $memberId, $eventId, $amount);
        try {
            $session = $this->gateway->createCheckoutSession($this->sessionParams($payment), $payment['id']);
        } catch (\Throwable $e) {
            $this->manager->cancelPayment($payment['id']);
            throw new InvalidArgumentException('Stripe did not create the checkout. '.$e->getMessage());
        }
        $this->manager->attachSession($payment['id'], $session['id'], $session['url']);
        return $session['url'];
    }
    private function sessionParams(array $payment): array {
        return [
            'mode' => 'payment',
            'client_reference_id' => $payment['id'],
            'line_items' => [['quantity'=>1, 'price_data'=>['currency'=>'cad', 'unit_amount'=>$payment['cents'], 'product_data'=>['name'=>$payment['label']]]]],
            'metadata' => ['payment_id'=>$payment['id']],
            'payment_intent_data' => ['metadata'=>['payment_id'=>$payment['id']]],
            'success_url' => $this->returnUrl.'?wpmm_payment=success',
            'cancel_url' => $this->returnUrl.'?wpmm_payment=cancelled',
            // Stripe accepts 30 minutes to 24 hours. An hour keeps unpaid holds short.
            'expires_at' => time() + 3600,
        ];
    }

    /** Returns the HTTP status for Stripe: 2xx stops retries, 4xx is a permanent rejection, 503 asks Stripe to retry. */
    public function handleWebhook(string $payload, string $signature): int {
        try {
            $event = $this->gateway->verifyEvent($payload, $signature);
        } catch (InvalidArgumentException) {
            return 400;
        }
        try {
            $type = $event['type']; $object = $event['data']['object'];
            if (str_starts_with($type, 'checkout.session.')) { $this->manager->applyCheckoutSession($type, $object); }
            elseif ($type === 'charge.refunded') { $this->manager->applyRefund($object); }
            return 200;
        } catch (InvalidArgumentException) {
            return 400;
        } catch (RuntimeException) {
            // Lock busy or database error. The event is not lost: Stripe will resend it.
            return 503;
        }
    }
}
