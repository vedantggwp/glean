# Support

Use GitHub issues for public support:

- Bug report: installation failures, queue/worker failures, delivery problems, or parsing errors.
- Feature request: new writer targets, prompt tuning ideas, review workflow improvements, or platform support.

Before filing an issue, please run:

```bash
python3 -m compileall scripts
PYTHONPATH="$PWD/scripts" python3 -m unittest discover -s tests -v
```

Include your OS, Python version, output mode, and relevant `worker.log` lines with secrets removed.

