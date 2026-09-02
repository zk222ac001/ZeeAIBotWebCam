# Vendor dependencies

The upstream Hiwonder TurboPi repository is intentionally **not copied** into this Git repository.

On Raspberry Pi, `scripts/bootstrap_pi.sh` clones:

```text
https://github.com/Hiwonder/TurboPi
```

into:

```text
vendor/TurboPi
```

That directory is ignored by Git so upstream vendor code remains separate from ZeeAIBotWebCam application code.

Production hardware access must go through the project hardware adapter boundary rather than arbitrary imports throughout the application.
