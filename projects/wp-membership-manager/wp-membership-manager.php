<?php
/**
 * Plugin Name: WP Membership Manager
 * Description: Association memberships, renewals, event sponsorships, Stripe test-mode card payments and consent-based HTML campaigns.
 * Version: 1.0.0
 * Requires at least: 6.6
 * Requires PHP: 8.2
 * Author: Jack Lai
 * License: MIT
 */
if (!defined('ABSPATH')) { exit; }
require_once __DIR__.'/src/Store.php';
require_once __DIR__.'/src/Manager.php';
require_once __DIR__.'/src/WordPressStore.php';
require_once __DIR__.'/src/CheckoutGateway.php';
require_once __DIR__.'/src/StripeGateway.php';
require_once __DIR__.'/src/Checkout.php';
require_once __DIR__.'/src/Admin.php';
function wpmm_manager(): \WPMM\Manager {
    global $wpdb;
    return new \WPMM\Manager(new \WPMM\WordPressStore($wpdb), wp_date('Y-m-d'));
}
/** Card payments read Stripe test keys from environment variables. Live keys are refused. */
function wpmm_checkout(): \WPMM\Checkout {
    $gateway = new \WPMM\StripeGateway((string)getenv('WPMM_STRIPE_SECRET_KEY'), (string)getenv('WPMM_STRIPE_WEBHOOK_SECRET'),
        function(string $method, string $url, array $headers, string $body): array {
            $response = wp_remote_request($url, ['method'=>$method, 'headers'=>$headers, 'body'=>$body, 'timeout'=>20]);
            if (is_wp_error($response)) { throw new \RuntimeException('Stripe could not be reached.'); }
            return ['status'=>(int)wp_remote_retrieve_response_code($response), 'body'=>(string)wp_remote_retrieve_body($response)];
        });
    return new \WPMM\Checkout(wpmm_manager(), $gateway, home_url('/'));
}
/** Stripe posts here. The signature is checked before any state changes. */
function wpmm_stripe_webhook(): void {
    $payload = (string)file_get_contents('php://input');
    $signature = is_string($_SERVER['HTTP_STRIPE_SIGNATURE'] ?? null) ? $_SERVER['HTTP_STRIPE_SIGNATURE'] : '';
    try { $status = wpmm_checkout()->handleWebhook($payload, $signature); }
    catch (\Throwable) { $status = 503; } // Missing keys or a busy database: ask Stripe to retry.
    status_header($status); nocache_headers(); exit;
}
register_activation_hook(__FILE__, function() { global $wpdb; (new \WPMM\WordPressStore($wpdb))->install(); update_option('wpmm_schema', 1); });
add_action('plugins_loaded', function() {
    if ((int)get_option('wpmm_schema') !== 1) { global $wpdb; (new \WPMM\WordPressStore($wpdb))->install(); update_option('wpmm_schema', 1); }
});
add_action('admin_menu', fn()=>add_menu_page('Membership Manager','Membership Manager','manage_options','wpmm',[\WPMM\Admin::class,'render'],'dashicons-groups'));
add_action('admin_post_wpmm_export_report', [\WPMM\Admin::class,'exportReport']);
add_action('admin_post_wpmm_save', [\WPMM\Admin::class,'handle']);
add_action('admin_post_nopriv_wpmm_stripe_webhook', 'wpmm_stripe_webhook');
add_action('admin_post_wpmm_stripe_webhook', 'wpmm_stripe_webhook');
// SMTP is opt-in. Normal installations keep their existing wp_mail transport.
// wp_mail validates From before phpmailer_init; localhost is not a valid mail domain.
add_filter('wp_mail_from', fn($from)=>getenv('WPMM_DEMO_SMTP') === '1' ? 'association@example.test' : $from);
add_filter('wp_mail_from_name', fn($name)=>getenv('WPMM_DEMO_SMTP') === '1' ? 'Demo Association' : $name);
add_action('phpmailer_init', function($mailer) {
    if (getenv('WPMM_DEMO_SMTP') === '1') {
        $mailer->isSMTP(); $mailer->Host = 'mailpit'; $mailer->Port = 1025;
        $mailer->SMTPAuth = false; $mailer->SMTPAutoTLS = false;
        $mailer->setFrom('association@example.test','Demo Association'); $mailer->Timeout = 5;
    }
});
add_action('template_redirect', function() {
    if (isset($_GET['wpmm_open'])) {
        $token = is_string($_GET['wpmm_open']) ? wp_unslash($_GET['wpmm_open']) : '';
        try { wpmm_manager()->open($token); } catch (\Throwable) { /* A busy writer must not break an email image. */ }
        nocache_headers(); header('Cache-Control: no-store, private'); header('Content-Type: image/gif');
        echo base64_decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'); exit;
    }
    if (isset($_GET['wpmm_unsubscribe'])) {
        $token = is_string($_GET['wpmm_unsubscribe']) ? wp_unslash($_GET['wpmm_unsubscribe']) : '';
        nocache_headers(); header('Referrer-Policy: no-referrer');
        $app = wpmm_manager();
        if (!$app->validToken($token)) { wp_die('Invalid unsubscribe link.', 'Unsubscribe', ['response'=>404]); }
        if ($_SERVER['REQUEST_METHOD'] === 'POST') {
            $posted = isset($_POST['confirm']) && is_string($_POST['confirm']) ? wp_unslash($_POST['confirm']) : '';
            if (!hash_equals($token, $posted)) { wp_die('Invalid confirmation.', 'Unsubscribe', ['response'=>403]); }
            try { $app->unsubscribe($token); } catch (\Throwable) { wp_die('Please retry shortly.', 'Unsubscribe', ['response'=>503]); }
            wp_die('You have been unsubscribed from membership emails.', 'Unsubscribed', ['response'=>200]);
        }
        $form = '<p>Stop receiving membership campaign emails?</p><form method="post"><input type="hidden" name="confirm" value="'.esc_attr($token).'"><button type="submit">Confirm unsubscribe</button></form>';
        wp_die($form, 'Unsubscribe', ['response'=>200]);
    }
});
