# Secret rotation and recovery drills

Use only synthetic credentials during the deferred test drill. Do not place credentials in command arguments, source archives, screenshots, shell history or shared support logs. Record credential identifiers/generations and results, never values.

**Provider connection:** use the connection owner's existing rotation action. The new credential uses the current project/connection/provider context and a fresh ciphertext reference; the old generation loses authorization for queued work. Check that old-generation plans fail, catalog refresh requires the current key and revoked work cannot retain a late result. Revoke the old key at the provider separately. Test references can demonstrate local behavior; only an authorized live provider can confirm remote revocation.

**GitHub operator credentials:** stop the importer/scheduler/webhook intake, use the existing protected initialization/staging process, rotate the corresponding provider-side private/client/webhook key deliberately, reauthorize repositories where required and test one bounded delivery. A changed signing secret cannot retrospectively authenticate an older forged event. Do not automatically reinstall or increase repository permissions.

**Authentication master:** no automatic online master rotation exists in phase 14. A manual overwrite would strand MFA seeds. Coordinate a backup and tested offline re-encryption design before rotating; for a lost or wrong file, restore the original. User factor re-enrollment is a distinct action and does not rotate the application master.

**AI encryption master:** the same rule applies: do not replace it over retained ciphertext. Existing initializer protections reject a new key over retained data. Use the original protected material during restoration. A future master-version/re-encryption workflow needs its own tested migration and crash-recovery protocol.

**Database passwords:** the restricted staging operator/runtime credentials are distinct. During a stopped-writer maintenance window, change the target role password and its private configuration together; verify API access with the intended role and rejection of the old secret. Keep a recoverable operator route until the new connection succeeds. Do not weaken the runtime role to make an error disappear.

The executed source tests cover local credential rotation/revocation and MFA reset/re-enrollment behavior, plus wrong-key restoration rejection. Live provider rotations, native role/password changes, host ACL checks and deployed process interruption have not been verified here. Record those results during staging instead of marking them complete from unit tests.
