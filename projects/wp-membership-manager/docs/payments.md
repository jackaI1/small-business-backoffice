# Card payments: design and states

Card payments use Stripe Checkout in test mode. The site creates a hosted payment page on Stripe's side, so card numbers never reach WordPress. A place or renewal changes only in response to a signed webhook from Stripe, never because the member was redirected back to the site.

## Configuration

| Variable | Purpose |
| --- | --- |
| `WPMM_STRIPE_SECRET_KEY` | Secret API key. Must start with `sk_test_`; live keys are refused in code. |
| `WPMM_STRIPE_WEBHOOK_SECRET` | Signing secret for the webhook endpoint, starting with `whsec_`. |

Webhook endpoint: `https://<site>/wp-admin/admin-post.php?action=wpmm_stripe_webhook`

Events to subscribe to: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`, `charge.refunded`. Other events are acknowledged and ignored.

Success and cancel redirects go to the site's home page with `?wpmm_payment=success` or `cancelled`. Neither changes any record.

## Components

- `src/StripeGateway.php`: the only code that talks to Stripe. It sends `POST /v1/checkout/sessions` with an `Idempotency-Key` (`wpmm-<payment id>`) and verifies webhook signatures. The HTTP call is injected, so WordPress supplies `wp_remote_request` and tests supply a fake.
- `src/Checkout.php`: creates payment links and turns verified events into handler calls. It returns the HTTP status that Stripe sees.
- `src/Manager.php`: owns every state change: the payment record, the registration hold, the renewal ledger and refunds. It has no Stripe code, so it is tested against an in-memory store.
- `src/Admin.php`: the admin forms and the Card payments table.
- `wp-membership-manager.php`: the `wpmm_checkout()` factory and the webhook entry point.

## Payment states

```
pending ──(Stripe session created)──> open ──(completed, paid)──────────> paid ──(full refund)──> refunded
   │                                   │  ├─(completed, unpaid)──> processing ─(async succeeded)─> paid
   │                                   │  │                              └─(async failed)──────> failed
   │                                   │  └─(expired)───────────────────────────────────────────> expired
   └─(Stripe refused the request)──> failed
any state: amount or currency differs from the stored payment ──> review
```

Final states (`paid`, `refunded`, `review`, `expired`, `failed`) ignore later events, so a repeated or late webhook changes nothing.

## Registration holds

A paid event place is stored as a registration with status `pending_payment` when the link is created. Pending and confirmed places count against capacity. The place becomes `confirmed` on a paid webhook, and `released` when the session expires or fails. A full refund sets it to `refunded`, which also frees the place. A session expires one hour after creation, so unpaid holds do not stay open long. If Stripe never delivers the expiry webhook, the hold stays until the event is resent. The Card payments table shows each open payment.

## Renewals and the receipt ledger

A paid renewal calls the same `recordRenewal` path as a manual receipt, with the receipt ID `stripe-<payment id>`. Receipts are unique, so a replayed webhook returns without extending the membership again. The extension follows the existing rule: from today if expired, otherwise from the current expiry.

## Refunds

`charge.refunded` carries the cumulative `amount_refunded`, so the handler sets the value rather than adding to it. A partial refund is recorded on the payment and the renewal, and the report subtracts it. A full refund changes the status to `refunded`. The membership expiry is not shortened automatically, because the later receipts and manual edits would make an automatic reversal ambiguous. An administrator decides that case.

## Failure handling

- Unknown or malformed webhook: rejected with 400 or acknowledged with 200 and no change.
- Bad signature, a timestamp more than five minutes old, or a session ID that does not match the payment: 400, no state change.
- Database lock busy or database error: 503, so Stripe resends the event later.
- Stripe refuses or cannot be reached while creating a link: the hold is released, the payment becomes `failed`, and the admin sees the reason.
- Missing or live keys: card forms show an error and the webhook returns 503 until the configuration is fixed.

## Limits

- The tests mock Stripe's HTTP responses and use Stripe's documented signature scheme. They have not been run against a live Stripe test account.
- Member self-service checkout is not built. An administrator creates each link and sends it to the member.
- The success page is the home page. Confirmation appears in the admin table after the webhook arrives.
- Payment amounts are fixed to the stored event fee or renewal fee. Stripe currency is CAD only.
