# Contributing

Thanks for helping. These are animation tools first: they should stay simple
to use, never get in the way of animating, and never touch your scene file.

## Reporting problems and ideas

Use [Issues](https://github.com/Marek-672/Maya-Tools/issues/new/choose). For a
problem, the form asks for the tool version, your Maya and system, what
happened, and the logs. Please leave out anything from a studio production
(shot names, rigs, footage, file paths you can't share).

## Changing the code

1. Fork the repository and make a branch.
2. Keep each change small and about one thing.
3. Run the tests before you open a pull request:
   ```
   cd bgcache
   python tests/run_tests.py
   ```
   They need no Maya (Maya and Qt are stubbed) and also run automatically on
   Windows, macOS and Linux for every pull request.
4. Test in a real Maya too if you can, and say which version and system in
   the pull request.

For BGCache, `bgcache/bgcache/DEVELOPER.md` maps the code and lists the rules
it keeps (for example: nothing extra in the hidden Maya's render path, every
"catch any error" says why, no function over 80 lines), and
`bgcache/bgcache/HOW_IT_WORKS.md` explains how the processes talk.

Studios: your own settings go in a pipeline profile
(`bgcache/PIPELINE_SETUP.md`), not in the shared code.

## Code of conduct

Be kind and constructive, as you would in a dailies room. Harassment or
personal attacks aren't welcome and will be removed.

By contributing you agree that your contribution is released under the
repository's MIT licence.
