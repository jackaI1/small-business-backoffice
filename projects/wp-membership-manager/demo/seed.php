<?php
// Invoked by wp eval-file after plugin activation. Synthetic data only.
$app = wpmm_manager();
if ($app->records('member') || $app->records('event')) { WP_CLI::success('Existing data preserved; seed skipped.'); return; }
$today = new DateTimeImmutable(wp_date('Y-m-d'));
$app->saveEvent(['id'=>'e1','name'=>'Student Research Night','date'=>$today->modify('+45 days')->format('Y-m-d'),'capacity'=>30]);
$members = [
    ['m1','Alex Example','student','+10 days',true],
    ['m2','Morgan Example','professional','+20 days',true],
    ['m3','Taylor Example','student','-10 days',true],
    ['m4','Riley Example','professional','+180 days',true],
    ['m5','Casey Example','student','+15 days',false],
];
foreach ($members as [$id,$name,$level,$expiry,$consent]) {
    $app->saveMember(['id'=>$id,'name'=>$name,'email'=>strtolower(explode(' ',$name)[0]).'@example.test','level'=>$level,'expires'=>$today->modify($expiry)->format('Y-m-d'),'consent'=>$consent]);
}
$app->renew('m4','demo-receipt-1','75.00');
$app->register('e1','m1'); $app->register('e1','m2');
$app->saveSponsor(['id'=>'s1','name'=>'Example Instruments','event'=>'e1','amount'=>'1500','paid'=>'500','agreement'=>'Programme logo and two reserved seats. Payment due before the event.']);
$app->saveSponsor(['id'=>'s2','name'=>'Example Materials','event'=>'e1','amount'=>'750','paid'=>'750','agreement'=>'Refreshment sponsor acknowledgement.']);
$app->createCampaign('Membership renewal reminder','<h1>Your association membership</h1><p>Hello {{name}},</p><p>Your membership is due within 30 days. Reply to the association to arrange renewal.</p>','due');
WP_CLI::success('Seeded 5 members, 1 renewal, 1 event, 2 registrations, 2 agreements and a 2-recipient draft.');
