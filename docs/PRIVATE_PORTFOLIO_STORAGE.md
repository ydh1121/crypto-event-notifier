# Private portfolio storage contract

This document defines the privacy boundary for future invited users. It does not change PAPER trading semantics.

## 1. Current owner

The current owner-managed holdings and averaging plans remain authoritative in the local journal SQLite database. `BackupManager` makes SQLite backup copies and, when `RCLONE_REMOTE` is configured, uploads those database backups to Google Drive. Cloudflare Pages remains a read-first surface and must never receive exchange API secrets.

## 2. Future invited users

An invited user's balances, average prices, averaging plans and exchange allocation are private to that user. They must not be stored as operator-readable JSON in D1, a Google Sheet, logs, Git, or analytics.

The required model is client-side zero-knowledge encryption:

1. The browser creates a random 256-bit data-encryption key (DEK).
2. Portfolio payloads are encrypted in the browser with AES-256-GCM and a unique random nonce per write.
3. The DEK is wrapped by a key-encryption key derived from a user-controlled recovery secret. A browser-native first implementation may use PBKDF2-SHA-256 with a high iteration count; an audited Argon2id implementation is preferred when a maintained dependency is adopted.
4. Cloud storage receives only ciphertext, nonce, salt, wrapped key, version and non-sensitive timestamps/IDs.
5. The server/operator never receives the plaintext recovery secret or unwrapped DEK.
6. Recovery is user-controlled. If the user loses every authorized device and recovery secret, the operator cannot decrypt the portfolio.

## 3. Google Sheets / Drive

A Google Sheet can be used only as a ciphertext transport/archive if the owner must be unable to read user assets. Native readable cells such as `BTC 0.5` or `평단 70000000` would contradict the zero-knowledge requirement.

If a Sheet mirror is added, each row should contain only fields such as:

- user opaque ID
- encrypted payload (base64)
- nonce
- wrapped DEK
- KDF salt/parameters
- schema version
- updated timestamp

The Google service credential may write ciphertext but must never possess the user decryption key.

## 4. Default exchange selection

The UI chooses the initial exchange after the user's holdings have been decrypted in the client/session:

- Bithumb holdings only -> Bithumb
- Upbit holdings only -> Upbit
- both -> exchange with the larger current holding value
- no usable holdings -> Bithumb

For the current legacy owner snapshot, holdings without an explicit `exchange` field are treated as Bithumb. Manual exchange changes remain available after the initial selection.

Do not leak per-exchange balances merely to implement the default. For zero-knowledge invited-user data, compute this preference after client-side decryption and store only the user's UI preference locally unless the user explicitly opts to sync it.

## 5. Safety boundary

Portfolio storage, calculators and preferences must never be coupled to live-order permissions. A calculator write is personal-data storage, not an instruction to place an order. Pages must remain unable to arm live trading or send exchange orders.
