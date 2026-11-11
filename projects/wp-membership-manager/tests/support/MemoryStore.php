<?php
use WPMM\Store;

final class MemoryStore implements Store {
    public array $rows = [];
    public function get(string $kind, string $key): ?array { return $this->rows[$kind][$key] ?? null; }
    public function all(string $kind): array { return array_values($this->rows[$kind] ?? []); }
    public function put(string $kind, string $key, array $data): void { $this->rows[$kind][$key] = $data; }
    public function atomic(callable $work, bool $transaction = true): mixed {
        $before = $this->rows;
        try { return $work(); } catch (Throwable $e) { $this->rows = $before; throw $e; }
    }
}
