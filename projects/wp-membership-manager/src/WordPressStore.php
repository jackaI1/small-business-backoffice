<?php
namespace WPMM;

final class WordPressStore implements Store {
    private string $table;
    private int $depth = 0;
    public function __construct(private \wpdb $db) { $this->table = $db->prefix.'wpmm_records'; }
    public function install(): void {
        require_once ABSPATH.'wp-admin/includes/upgrade.php';
        $charset = $this->db->get_charset_collate();
        dbDelta("CREATE TABLE {$this->table} (
            id bigint unsigned NOT NULL AUTO_INCREMENT,
            kind varchar(20) NOT NULL,
            record_key varchar(120) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            payload longtext NOT NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY kind_record (kind,record_key)
        ) ENGINE=InnoDB $charset;");
        if ($this->db->last_error) { throw new \RuntimeException('Could not create membership table.'); }
    }
    public function get(string $kind, string $key): ?array {
        $json = $this->db->get_var($this->db->prepare("SELECT payload FROM {$this->table} WHERE kind=%s AND record_key=%s", $kind, $key));
        if ($this->db->last_error) { throw new \RuntimeException('Could not read membership data.'); }
        return $json === null ? null : json_decode($json, true, 512, JSON_THROW_ON_ERROR);
    }
    public function all(string $kind): array {
        $rows = $this->db->get_col($this->db->prepare("SELECT payload FROM {$this->table} WHERE kind=%s ORDER BY record_key", $kind));
        if ($this->db->last_error) { throw new \RuntimeException('Could not read membership data.'); }
        return array_map(fn($json)=>json_decode($json, true, 512, JSON_THROW_ON_ERROR), $rows);
    }
    public function put(string $kind, string $key, array $data): void {
        $sql = $this->db->prepare("INSERT INTO {$this->table} (kind,record_key,payload) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)", $kind, $key, wp_json_encode($data, JSON_THROW_ON_ERROR));
        if ($this->db->query($sql) === false) { throw new \RuntimeException('Could not save membership data.'); }
    }
    public function atomic(callable $work, bool $transaction = true): mixed {
        if ($this->depth > 0) { return $work(); }
        $lock = 'wpmm_'.hash('sha256', DB_NAME.$this->table);
        $lock = substr($lock, 0, 64);
        if ((int)$this->db->get_var($this->db->prepare('SELECT GET_LOCK(%s,0)', $lock)) !== 1) { throw new \RuntimeException('Another membership update is running. Please retry.'); }
        ++$this->depth;
        try {
            if ($transaction && $this->db->query('START TRANSACTION') === false) { throw new \RuntimeException('Could not start transaction.'); }
            $result = $work();
            if ($transaction && $this->db->query('COMMIT') === false) { throw new \RuntimeException('Could not commit update.'); }
            return $result;
        } catch (\Throwable $e) {
            if ($transaction) { $this->db->query('ROLLBACK'); }
            throw $e;
        } finally {
            --$this->depth; $this->db->get_var($this->db->prepare('SELECT RELEASE_LOCK(%s)', $lock));
        }
    }
}
