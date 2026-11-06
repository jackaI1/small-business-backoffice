<?php
namespace WPMM;

interface Store {
    public function get(string $kind, string $key): ?array;
    public function all(string $kind): array;
    public function put(string $kind, string $key, array $data): void;
    /** Serialize writers and roll back on exceptions. */
    public function atomic(callable $work, bool $transaction = true): mixed;
}
