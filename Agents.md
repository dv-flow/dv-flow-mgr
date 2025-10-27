
# Setting up the Project
This project has several dependencies, which are managed by the `ivpm` tool. Bootstrap the project using the following commands:
```
% python3 -m venv packages/python
% ./packages/python/bin/pip install -U ivpm
% ./packages/python/bin/ivpm update -a
```
Note: Use anonymous ('-a') mode when running in a CI/CD action.

# Running Tests
Tests can be run as follows:

```
% PYTHONPATH=$(pwd)/src ./packages/python/bin/pytest -s tests/unit
```

