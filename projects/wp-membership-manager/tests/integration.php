<?php
// Real WordPress/MariaDB adapter checks, in an owned table removed even on failure.
use WPMM\Manager;
use WPMM\WordPressStore;
$db = new wpdb(DB_USER, DB_PASSWORD, DB_NAME, DB_HOST);
$db->set_prefix($GLOBALS['wpdb']->prefix.'wpmm_test_');
$table = $db->prefix.'wpmm_records';
$store = new WordPressStore($db); $store->install();
$app = new Manager($store, '2026-06-01'); $checks = 0;
$check = function($condition, $message) use (&$checks) { if (!$condition) { throw new RuntimeException($message); } ++$checks; };
try {
    $app->saveEvent(['id'=>'e1','name'=>'Integration Event','date'=>'2026-07-01','capacity'=>1]);
    $csv = file_get_contents(__DIR__.'/../demo/salesforce-report.csv');
    $check($app->importCsv($csv) === 3, 'CSV row count');
    $app->importCsv($csv); $check($app->report()['members'] === 2, 'CSV upsert');
    $check($app->report()['sponsor_outstanding_cents'] === 100000, 'Sponsor report');
    $app->renew('003-demo-1','integration-r1','25.50'); $app->renew('003-demo-1','integration-r1','25.50');
    $check($app->report()['renewals'] === 1 && $app->report()['renewal_cents'] === 2550, 'Idempotent receipt');
    $app->register('e1','003-demo-1'); $app->register('e1','003-demo-1');
    try { $app->register('e1','003-demo-2'); throw new RuntimeException('Overbooked'); } catch (InvalidArgumentException) { ++$checks; }
    $app->saveMember(['id'=>'first','name'=>'Rollback Example','email'=>'rollback@example.test','level'=>'student','expires'=>'2026-06-20','consent'=>true]);
    $bad = str_replace('Alex Example,alex@example.test', 'Changed Example,changed@example.test', $csv);
    $bad = str_replace('Sam Example,sam@example.test','Sam Example,invalid', $bad);
    try { $app->importCsv($bad); throw new RuntimeException('Accepted bad CSV'); } catch (InvalidArgumentException) { ++$checks; }
    $check($store->get('member','003-demo-1')['email'] === 'alex@example.test', 'Real transaction rollback');
    $before = $app->report()['members'];
    foreach (['CaseMember','casemember'] as $i=>$id) {
        $app->saveMember(['id'=>$id,'name'=>'Case Example','email'=>"case$i@example.test",'level'=>'student','expires'=>'2028-01-01','consent'=>false]);
    }
    $check($app->report()['members'] === $before + 2, 'External IDs preserve case without overwriting another member');
    try { $app->register('E1','CaseMember'); throw new RuntimeException('Case-variant event ID accepted'); } catch (InvalidArgumentException) { ++$checks; }
    add_action('wp_mail_failed', fn($error)=>WP_CLI::warning($error->get_error_message()));
    $id=$app->createCampaign('Integration HTML Test','<h1>Hello {{name}}</h1>','due');
    $check($app->send($id,fn($to,$subject,$html)=>wp_mail($to,$subject,$html,['Content-Type: text/html; charset=UTF-8']),home_url()) === 1, 'SMTP send');
    $check($app->send($id,fn()=>true,home_url()) === 0, 'No resend');
    $token=$app->deliveries($id)[0]['token']; $app->open($token); $app->open($token);
    $check($app->report()['opened'] === 1, 'Unique open');
    $app->unsubscribe($token); $app->importCsv($csv);
    $check(count($app->segment('due')) === 0, 'Unsubscribe persists');
    // A second database connection must not interleave membership writers.
    $other = new wpdb(DB_USER, DB_PASSWORD, DB_NAME, DB_HOST); $other->set_prefix($db->prefix);
    $otherStore = new WordPressStore($other);
    $store->atomic(function() use ($otherStore, &$checks) {
        try { $otherStore->atomic(fn()=>null); throw new RuntimeException('Concurrent writer admitted'); }
        catch (RuntimeException $e) { if (!str_contains($e->getMessage(),'Another membership update')) { throw $e; } ++$checks; }
    });
    WP_CLI::success("$checks real-database integration checks passed.");
} finally { $db->query("DROP TABLE IF EXISTS $table"); }
