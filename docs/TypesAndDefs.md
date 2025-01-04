
Package is a properly-parameterized PackageDef instance. We know where to look
for imports, but may not have processed the data yet (lazy loading).
Package still contains TaskDefs, but they are a bit more refined. Specifically,
we will have incorporated parameters from base types. 