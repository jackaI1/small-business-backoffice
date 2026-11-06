<?php
namespace WPMM;

final class Admin {
    public static function handle(): void {
        if (!current_user_can('manage_options')) { wp_die('Administrators only.', 'Forbidden', ['response'=>403]); }
        check_admin_referer('wpmm_save');
        $get = static function(string $key): string {
            $value = $_POST[$key] ?? '';
            if (!is_string($value)) { throw new \InvalidArgumentException('Invalid field.'); }
            return trim(wp_unslash($value));
        };
        try {
            $app = wpmm_manager(); $task = $get('task'); $message = 'Saved.';
            switch ($task) {
                case 'member': $app->saveMember(['id'=>$get('id'),'name'=>sanitize_text_field($get('name')),'email'=>$get('email'),'level'=>sanitize_text_field($get('level')),'expires'=>$get('expires'),'consent'=>$get('consent') === 'yes']); break;
                case 'renew': $app->renew($get('member'),$get('receipt'),$get('amount')); break;
                case 'event': $app->saveEvent(['id'=>$get('id'),'name'=>sanitize_text_field($get('name')),'date'=>$get('date'),'capacity'=>$get('capacity')]); break;
                case 'sponsor': $app->saveSponsor(['id'=>$get('id'),'name'=>sanitize_text_field($get('name')),'event'=>$get('event'),'amount'=>$get('amount'),'paid'=>$get('paid'),'agreement'=>sanitize_text_field($get('agreement'))]); break;
                case 'register': $app->register($get('event'),$get('member')); break;
                case 'campaign': $id = $app->createCampaign($get('subject'),wp_kses_post($get('html')),$get('segment')); $message = 'Draft created. Review its recipients below, then send batch: '.$id; break;
                case 'send': $sent = $app->send($get('campaign'),fn($to,$subject,$html)=>wp_mail($to,$subject,$html,['Content-Type: text/html; charset=UTF-8']),home_url()); $message = "$sent emails accepted by the mail transport in this batch."; break;
                case 'import':
                    $file = $_FILES['csv'] ?? [];
                    if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK || !is_string($file['tmp_name'] ?? null) || !is_uploaded_file($file['tmp_name']) || (int)($file['size'] ?? 0) > 1048576) { throw new \InvalidArgumentException('Upload a CSV file of at most 1 MiB.'); }
                    $csv = file_get_contents($file['tmp_name']); if ($csv === false) { throw new \RuntimeException('Could not read upload.'); }
                    $message = $app->importCsv($csv).' report rows imported.'; break;
                default: throw new \InvalidArgumentException('Unknown action.');
            }
            set_transient('wpmm_notice_'.get_current_user_id(), ['ok'=>true,'message'=>$message], 60);
        } catch (\Throwable $e) {
            $message = $e instanceof \InvalidArgumentException ? $e->getMessage() : 'The update could not finish. Please retry, or check the server database and mail configuration.';
            set_transient('wpmm_notice_'.get_current_user_id(), ['ok'=>false,'message'=>$message], 60);
        }
        wp_safe_redirect(admin_url('admin.php?page=wpmm')); exit;
    }
    public static function exportReport(): void {
        if (!current_user_can('manage_options')) { wp_die('Administrators only.', 'Forbidden', ['response'=>403]); }
        check_admin_referer('wpmm_export_report');
        nocache_headers();
        header('Content-Type: text/csv; charset=UTF-8');
        header('Content-Disposition: attachment; filename="membership-summary.csv"');
        echo wpmm_manager()->reportCsv(); exit;
    }
    private static function form(string $task, string $title, array $fields, string $button = 'Save'): void {
        echo '<details class="wpmm-form"><summary>'.esc_html($title).'</summary><form method="post" enctype="multipart/form-data" action="'.esc_url(admin_url('admin-post.php')).'">';
        wp_nonce_field('wpmm_save'); echo '<input type="hidden" name="action" value="wpmm_save"><input type="hidden" name="task" value="'.esc_attr($task).'">';
        foreach ($fields as $name=>$field) {
            [$label,$type,$default] = array_pad($field,3,'');
            echo '<p><label>'.esc_html($label).'<br>';
            if (is_array($type)) {
                echo '<select name="'.esc_attr($name).'">'; foreach ($type as $value=>$text) { echo '<option value="'.esc_attr($value).'">'.esc_html($text).'</option>'; } echo '</select>';
            } elseif ($type === 'textarea') { echo '<textarea rows="6" cols="65" name="'.esc_attr($name).'" required>'.esc_textarea($default).'</textarea>'; }
            else { echo '<input required type="'.esc_attr($type).'" name="'.esc_attr($name).'" value="'.esc_attr($default).'" '.($type === 'file' ? 'accept=".csv,text/csv"' : '').'>'; }
            echo '</label></p>';
        }
        submit_button($button); echo '</form></details>';
    }
    private static function table(string $title, array $rows, array $columns): void {
        echo '<h2>'.esc_html($title).'</h2><div style="overflow-x:auto"><table class="widefat striped"><thead><tr>';
        foreach ($columns as $label) { echo '<th scope="col">'.esc_html($label).'</th>'; } echo '</tr></thead><tbody>';
        if (!$rows) { echo '<tr><td colspan="'.count($columns).'">No records yet.</td></tr>'; }
        foreach ($rows as $row) {
            echo '<tr>'; foreach ($columns as $key=>$label) { $value = $row[$key] ?? ''; if (is_bool($value)) { $value = $value ? 'Yes' : 'No'; } if (str_ends_with($key, 'cents')) { $value = '$'.number_format((int)$value / 100, 2); } echo '<td>'.esc_html((string)$value).'</td>'; } echo '</tr>';
        }
        echo '</tbody></table></div>';
    }
    public static function render(): void {
        if (!current_user_can('manage_options')) { wp_die('Administrators only.'); }
        $app = wpmm_manager(); $r = $app->report();
        echo '<div class="wrap"><h1>Membership Manager</h1><p>Keep member renewals, event places, sponsorship agreements and campaign results together. All amounts are CAD.</p>';
        $key = 'wpmm_notice_'.get_current_user_id(); $notice = get_transient($key); delete_transient($key);
        if ($notice) { echo '<div class="notice '.($notice['ok'] ? 'notice-success' : 'notice-error').'" role="status"><p>'.esc_html($notice['message']).'</p></div>'; }
        echo '<h2>Association overview</h2><dl style="display:flex;flex-wrap:wrap;gap:24px">';
        $labels = ['members'=>'Members','active'=>'Active memberships','due'=>'Renewals due within 30 days','renewals'=>'Renewal receipts','renewed_members'=>'Members renewed','renewal_cents'=>'Renewal payments','registrations'=>'Event registrations','sponsor_cents'=>'Sponsorship pledged','sponsor_paid_cents'=>'Sponsorship paid','sponsor_outstanding_cents'=>'Sponsorship outstanding','sent'=>'Emails accepted','opened'=>'Unique recorded opens','failed'=>'Failed emails'];
        foreach ($labels as $key=>$label) { $value = str_ends_with($key,'cents') ? '$'.number_format($r[$key]/100,2) : $r[$key]; echo '<div><dt>'.esc_html($label).'</dt><dd style="font-size:24px;margin:8px 0">'.esc_html((string)$value).'</dd></div>'; }
        echo '</dl><p><a class="button" href="'.esc_url(wp_nonce_url(admin_url('admin-post.php?action=wpmm_export_report'), 'wpmm_export_report')).'">Download summary CSV</a> Aggregate totals only, without member names or email addresses.</p><p>Reports are all-time. Due dates include today and the next 30 days. Opens count each delivered message once; blocked images and privacy proxies make them approximate. Accepted emails are not proof of inbox delivery.</p><h2>Add or update records</h2><p>Reuse an ID to update a member, event or agreement. Use a new receipt ID for each annual renewal. Imported IDs stay the same across repeated uploads. Unsubscribed members stay opted out.</p><style>.wpmm-form{border:1px solid #c3c4c7;background:white;padding:14px;margin:10px 0;max-width:850px}.wpmm-form summary{cursor:pointer;font-weight:600}.wpmm-form input:not([type=hidden]),.wpmm-form textarea{max-width:100%;width:480px}</style>';
        self::form('member','Member details',['id'=>['Member ID','text'],'name'=>['Full name','text'],'email'=>['Email','email'],'level'=>['Membership level','text','student'],'expires'=>['Membership expires','date'],'consent'=>['Permission to receive campaigns',['no'=>'No','yes'=>'Yes']]]);
        self::form('renew','Record an annual renewal',['member'=>['Member ID','text'],'receipt'=>['Unique receipt ID','text'],'amount'=>['Payment in CAD (for example 25.00)','text']]);
        self::form('event','Event details',['id'=>['Event ID','text'],'name'=>['Event name','text'],'date'=>['Event date','date'],'capacity'=>['Capacity','number']]);
        self::form('register','Register a member for an event',['event'=>['Event ID','text'],'member'=>['Member ID','text']]);
        self::form('sponsor','Sponsorship agreement',['id'=>['Agreement ID','text'],'name'=>['Sponsor name','text'],'event'=>['Event ID','text'],'amount'=>['Total pledge in CAD','text'],'paid'=>['Paid to date in CAD','text'],'agreement'=>['Agreed benefits and obligations','textarea']]);
        self::form('import','Import a Salesforce detail-report CSV',['csv'=>['CSV file, maximum 1 MiB and 2000 rows','file']], 'Import rows');
        echo '<p>Use the headers in <code>demo/salesforce-report.csv</code>. Create referenced events first. This imports exported files; it does not connect to Salesforce.</p><h2>Email campaigns</h2><p>Create a draft, review the recipient list, then send. Each click sends up to 100 pending or failed messages. Successful messages are never sent twice. HTML supports {{name}} for the member name. Email consent is checked again before sending.</p>';
        $segments = ['due'=>'Renewals due within 30 days','active'=>'Active members','expired'=>'Expired members','all'=>'All consenting members'];
        foreach ($segments as $segment=>$label) { echo '<p>'.esc_html($label).': '.count($app->segment($segment)).' recipients</p>'; }
        self::form('campaign','Create an HTML email draft',['subject'=>['Subject','text'],'segment'=>['Audience',$segments],'html'=>['HTML message','textarea','<h1>Membership reminder</h1><p>Hello {{name}}, your membership is due soon. Please contact the association to renew.</p>']], 'Create draft');
        $campaigns = $app->records('campaign');
        foreach ($campaigns as $campaign) {
            $deliveries = $app->deliveries($campaign['id']);
            echo '<details><summary>Message preview: '.esc_html($campaign['subject']).'</summary><div style="max-width:680px;background:white;padding:20px">'.wp_kses_post($campaign['html']).'</div></details>';
            self::table($campaign['subject'].' ('.$campaign['segment'].')', $deliveries, ['name'=>'Recipient','email'=>'Email','status'=>'Delivery status','opened'=>'Recorded open']);
            self::form('send','Send next batch: '.$campaign['subject'],['campaign'=>['Campaign ID','text',$campaign['id']]], 'Send or retry batch');
        }
        self::table('Members', $app->records('member'), ['id'=>'ID','name'=>'Name','email'=>'Email','level'=>'Level','expires'=>'Expires','consent'=>'Campaign consent','source'=>'Source']);
        self::table('Renewal receipts', $app->records('renewal'), ['id'=>'Receipt','member'=>'Member ID','date'=>'Recorded','expires'=>'New expiry','cents'=>'Paid']);
        self::table('Events', $app->records('event'), ['id'=>'ID','name'=>'Event','date'=>'Date','capacity'=>'Capacity']);
        self::table('Registrations', $app->records('registration'), ['event'=>'Event ID','member'=>'Member ID','date'=>'Registered']);
        self::table('Sponsorship agreements', $app->records('sponsor'), ['id'=>'ID','name'=>'Sponsor','event'=>'Event ID','agreement'=>'Agreement','cents'=>'Pledged','paid_cents'=>'Paid']);
        echo '</div>';
    }
}
