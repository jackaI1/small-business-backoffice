# Membership Manager

This plugin keeps association memberships, renewal receipts, event registrations, sponsorship agreements and email campaign reports inside WordPress.

## People using it

Association administrators maintain records and send reminders from the WordPress admin dashboard. Only administrators can view member information or make changes.

## Local demo

The Docker Compose demo contains synthetic records and sends email to Mailpit, a local test inbox. It includes sample contact and opportunity report CSV files. The plugin imports those files without connecting directly to Salesforce.

## Interface

The dashboard follows WordPress admin conventions: labelled form controls, tables, notices and menu navigation. Reports appear before the forms, and the record tables help administrators check changes.

## Boundaries

Campaigns use explicit email permission and include unsubscribe confirmation links. Payments can be recorded manually or taken by card through Stripe's hosted test-mode checkout: an admin creates a payment link, and the place or renewal is confirmed only by a signed Stripe webhook. Sponsorship agreements store benefits and amounts; the plugin does not collect signatures. The README explains setup, everyday use, tests and operational limits.
