
# Named Fragments

Fragments contain package contents to be included into the containing package.
Currently, they are not a named scope. I want to allow fragments to be given
a name to make it simpler to ensure that all tasks have unique names.

```yaml
fragment:
  tasks:
  - name: my_t
    
```

If the fragment above was included in package 'pkg', the full taskname would
be pkg.my_t.

```yaml
fragment:
  name: c1
  tasks:
  - name: my_t
    
```

In a named fragment, tasks are named like this:
name == <pkg>[named fragment levels...].<taskname>. 
When using a named fragment, the task above is named
pkg.c1.my_t.

