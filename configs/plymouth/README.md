# Plymouth (boot splash)

Status: **draft placeholder — not packaged, not activated.**

`nexus/` contains a draft `script`-module theme. It is intentionally *not*
installed by any NexusOS package in v0.1.0 because a broken Plymouth theme can
hide boot errors or LUKS passphrase prompts.

Remaining work:
1. Render `logo.png` (from `branding/boot/nexusos-boot-logo.svg`, `#mark` layer),
   `progress-track.png` and `progress-fill.png` at build time.
2. Add password/question/message callbacks (`Plymouth.SetDisplayPasswordFunction`,
   `SetDisplayQuestionFunction`, `SetMessageFunction`) — required for encrypted disks.
3. Package under `/usr/share/plymouth/themes/nexus/` and register with
   `update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth … 100`
   in postinst, removing it in prerm; then `update-initramfs -u` (only in a VM/ISO build).
4. Test with `plymouthd --debug --tty=/dev/tty2 && plymouth --show-splash` in a VM,
   and an encrypted-disk install.
