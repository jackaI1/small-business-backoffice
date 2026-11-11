# wp-membership-manager

I built a WordPress plugin for association memberships, event places and renewals because I wanted to see how a club's records fit together, and because a club that runs events will eventually want to take card payments for them. This is a learning project.

## Try it locally

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) or another Docker engine with Compose, then run:

```sh
bash demo/setup.sh
```

Open [Membership Manager](http://localhost:8080/wp-admin/admin.php?page=wpmm) and sign in with **demo / local-demo-only**. These are public credentials for the local demo, not for a hosted site. The setup creates five members, two registrations, one renewal, two sponsorship agreements, and a draft reminder for two consenting members.

1. Click **Download summary CSV** in the association overview to save the current totals.
2. Open the draft's **Message preview** and check its recipient list.
3. Open **Send next batch: Membership renewal reminder** and click **Send or retry batch**.
4. Open [Mailpit](http://localhost:8025) to read the two emails. Show the message's HTML images to record an open. The unsubscribe link asks for confirmation before changing a member's email permission.
5. Back in WordPress, record a renewal using member ID `m1`, a new receipt ID such as `receipt-002`, and payment `25.00`. The expiry advances by one year and the payment appears in the report. Reusing that receipt does not add another payment.
6. Import `demo/salesforce-contacts.csv`, then `demo/salesforce-opportunities.csv` through **Import a Salesforce detail-report CSV**. The dashboard gains two members and a $2,000 pledge with $1,250 paid. Importing those files again updates the same records.

When finished, stop the demo and remove its synthetic database:

```sh
docker compose down -v --remove-orphans
```

To keep the demo records between sessions, use `docker compose down` without `-v`. If the default ports are busy, run `WP_PORT=8088 MAILPIT_PORT=8028 bash demo/setup.sh` and use those ports in the links. Keep the same `WP_PORT` on later starts because WordPress stores its address.

## Taking card payments in test mode

Stripe is a payments service. I use its **test mode**, which takes fake cards and moves no real money. Card payments are optional. Without test keys, the plugin works as before and the card section says payments are off.

Here is what an administrator can do:

- **Event place:** create a card payment link for a member and an event with a fee. The place is held while the link is open. It is confirmed only after Stripe tells the site the payment succeeded. If the link expires or the payment fails, the place goes back to the pool.
- **Renewal:** create a card payment link for a member and a fee. Once the payment is confirmed, the renewal is recorded in the receipt history once, and the membership moves forward one year. A repeated notice from Stripe cannot add a second year.
- **Refunds:** recorded automatically. A refunded place is released. A refunded renewal shows the refund in the report, but the expiry date does not move backwards. I decide that by hand.

The admin sends the payment link to the member. Members do not have a sign-up page in this plugin.

### Setup, about two minutes

1. Create a free [Stripe](https://dashboard.stripe.com/register) account and stay in **test mode**.
2. Copy the secret key that starts with `sk_test_` and set it as the environment variable `WPMM_STRIPE_SECRET_KEY`. The plugin refuses keys that start with `sk_live_`.
3. Add a webhook endpoint in Stripe at `https://your-site/wp-admin/admin-post.php?action=wpmm_stripe_webhook`. Subscribe to `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired` and `charge.refunded`. Copy its signing secret (starts with `whsec_`) into `WPMM_STRIPE_WEBHOOK_SECRET`.
4. Pay with the test card `4242 4242 4242 4242`, any future date and any three digits.

To test on your own computer, the Stripe command-line tool can forward events to the demo. Run `stripe listen --forward-to localhost:8080/wp-admin/admin-post.php?action=wpmm_stripe_webhook`, then set the signing secret it prints as `WPMM_STRIPE_WEBHOOK_SECRET` before running `bash demo/setup.sh`.

After paying, Stripe sends the member back to the site's home page. The place or renewal is confirmed by Stripe's webhook, not by that page, so the admin table is the place to check.

## What I keep track of

- **Memberships:** member ID, name, email, membership level, expiry date, and email permission. One email address belongs to one member ID.
- **Renewals:** an annual extension and a payment receipt, either entered by hand or paid by card. An expired membership restarts from today; an active membership extends from its current expiry.
- **Events:** date, capacity, an optional entry fee, and member registrations. A member cannot take two places at the same event, and a full event rejects another registration. Places held by unpaid card links count against capacity until they are paid or released.
- **Card payments:** each link's amount, status (open, paid, expired, refunded and so on), and any refund. Admins can open a link that is still waiting for payment.
- **Sponsorships:** the event, agreed benefits, total pledge, and amount paid. Pledged, paid, and outstanding amounts appear separately, in Canadian dollars.
- **Campaigns:** a saved audience and message, individual delivery outcomes, and unique recorded opens. Email permission is checked again just before sending.

I use **Add or update records** for changes. Reusing a member, event, or agreement ID updates that record. Receipts keep a history of renewals. The dashboard reports totals across all stored records; the due-soon group includes today through 30 days from today.

## Importing Salesforce report exports

I import exported CSV files, plain tables saved from a report. I do not connect to Salesforce or use its API. The sample files are synthetic examples of the supported report shapes; I have not tested against a live Salesforce account.

For a contact report, select **Details Only**, export CSV, and use these column labels:

```text
Contact ID,Full Name,Email,Membership Level,Membership Expiry,Email Opt Out
```

For a sponsorship opportunity report:

```text
Opportunity ID,Account Name,Event ID,Amount,Amount Paid,Agreement
```

Membership and event fields depend on the association's Salesforce configuration. Rename the exported headers to match these labels, use dates such as `2027-06-20`, amounts such as `1500.00`, and `true` or `false` for **Email Opt Out**. An opt-out suppresses campaigns; `false` is suitable only when the association already has permission to send. Create the referenced event in WordPress first. Keep Contact and Opportunity IDs stable across uploads.

I also include a combined format in `demo/salesforce-report.csv`. It overlaps the seeded Alex and Sam email addresses under different IDs, so importing it into the seeded demo correctly rejects the conflict. The two separate export samples above can be imported directly. [Import details](docs/imports.md) explain validation, limits, and repeat uploads.

## Installing on an existing WordPress site

Copy this folder to `wp-content/plugins/wp-membership-manager`, then activate **WP Membership Manager** under **Plugins**. It requires WordPress 6.6 or later, PHP 8.2 or later, and MySQL or MariaDB with InnoDB tables. Composer is only needed to run the tests, not to activate the plugin.

Only administrators can view the dashboard or change records. Outside the demo, the plugin uses the site's existing WordPress mail setup. Every campaign includes an unsubscribe link. I would configure a real mail provider, HTTPS, backups, a privacy notice, and the association's consent process before using real member data. Card payments should stay in test mode until the association has its own Stripe account, a privacy notice for payment data and a tested refund process.

## How I organised it

`wp-membership-manager.php` connects the plugin to WordPress, including the Stripe webhook address. `src/Admin.php` handles the dashboard, the summary download, permissions, form tokens and the card payments table. I edited the four title cards into the walkthrough with FFmpeg, a video editing tool; the cards and output are in `demo/video/`. `src/Manager.php` contains the membership, campaign, payment, reporting, and import rules. `src/Checkout.php` creates payment links and applies webhook events. `src/StripeGateway.php` is the only code that talks to Stripe, including the signature check. `src/WordPressStore.php` saves records in a dedicated database table with unique record IDs.

Money is stored as whole cents. Database transactions keep imports and renewals together, and a database lock prevents two writers from overbooking the same event or recording the same receipt twice. A card payment's amount and currency are checked against the stored payment before anything is confirmed. Campaigns send up to 100 messages per click. Each delivery gets a random link token, and successful messages are not resent. Failed sends can be retried. A process interrupted during a send leaves that delivery marked `sending`; I check the mail server before resolving an uncertain delivery. [Design and operational limits](docs/design.md) explain that tradeoff, and [card payments](docs/payments.md) describes the payment states, webhook events and refund handling.

An open means the message's tracking image was requested, not that a person definitely read it. Image blocking can hide opens, and email privacy tools can create them. The dashboard counts each sent message once even if its image is requested repeatedly. Mail acceptance also does not prove inbox delivery.

## Tests and limits

GitHub Actions runs two jobs on every change to this folder. The first installs PHP 8.4, lints every PHP file, and runs 53 PHPUnit tests. Those tests cover membership and receipt rules, Stripe checkout requests, registration holds, refunds, and webhook signature checks using signed fixture files. Stripe's network calls are replaced by a test double in those tests. The second job starts the demo in Docker with WordPress and MariaDB, runs the database integration checks inside WordPress, and drives the admin forms, Mailpit, and the webhook endpoint. The endpoint must refuse an unsigned or forged request and accept a correctly signed event that matches no payment on this site.

Limits I know about:

- I have not run card payments against a live Stripe test account. The CI job has no Stripe keys, so it checks the webhook path with signed test events but does not create a real Checkout session.
- Refunds do not shorten a membership. Stripe's webhooks can arrive late or out of order, and a stale hold after a lost expiry event stays until the event is resent.
- Deployment still needs the association's own mail, privacy, backup and consent setup.

This is a source snapshot of a learning project, not a production membership system.
