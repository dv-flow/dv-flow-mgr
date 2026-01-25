
# Task-Artifact Caching

**Status:** ✅ Implemented and Production-Ready

Caching the result of executing tasks can significantly shorten workflow runs. DV Flow supports comprehensive caching of task artifacts and outputs.

## Quick Start

### 1. Initialize a Cache

```bash
# Personal cache
dfm cache init ~/.cache/dv-flow
export DV_FLOW_CACHE=~/.cache/dv-flow

# Shared team cache
dfm cache init /shared/team/cache --shared
export DV_FLOW_CACHE=/shared/team/cache
```

### 2. Enable Caching in Tasks

```yaml
tasks:
  - name: build
    run: make all
    cache: true  # Simple enable
    
  - name: compile
    run: gcc -o app main.c
    cache:
      enabled: true
      compression: gzip
      hash:
        - shell("gcc --version")
        - env.CFLAGS
```

### 3. Run and Enjoy

First run executes normally and stores results in cache. Subsequent runs with identical inputs return instantly from cache!

## How It Works

### Cache Key Computation

For each cacheable task, a cache key is computed from:
- **Task name**
- **Input filesets** - MD5 hash of all consumed files
- **Parameters** - JSON serialization of task parameters
- **Extra hash expressions** - Custom expressions from `cache.hash`

The final key format is: `<taskname>:<md5_hash>`

### Cache Hit Flow

1. Task is ready to execute
2. Cache key computed from inputs
3. Cache providers queried for matching entry
4. **On hit:**
   - Output template restored (paths expanded from `${{ rundir }}`)
   - Artifacts extracted to task rundir
   - Task marked as complete without execution
   - Result marked with `cache_hit=True`

### Cache Miss Flow

1. Cache key computed but no entry found
2. Task executes normally
3. **On success:**
   - Output paths validated (must be within rundir)
   - Paths converted to `${{ rundir }}` templates for portability
   - Artifacts optionally compressed (gzip/bzip2)
   - Entry stored in all writable cache providers
   - Result marked with `cache_stored=True`

## TaskDef: Cache Configuration

### cache (bool or object)

Simple enable/disable:
```yaml
cache: true   # Enable with defaults
cache: false  # Explicitly disable
```

Detailed configuration:
```yaml
cache:
  enabled: true
  compression: gzip
  hash:
    - shell("gcc --version")
    - env.BUILD_MODE
```

### enabled (bool, default: true)

Controls whether caching is active for this task:
```yaml
cache:
  enabled: false  # Don't cache this task
```

### hash (list of expressions, default: [])

Additional expressions to include in cache key. Common uses:
- Tool versions: `shell("gcc --version")`
- Build flags: `env.CFLAGS`
- Configuration: `env.BUILD_MODE`

```yaml
cache:
  hash:
    - shell("${{ env.CC:-gcc }} --version")
    - shell("git rev-parse HEAD")
    - env.OPTIMIZATION_LEVEL:-O2
```

### compression (string, default: "no")

Controls artifact compression:
- `no` - No compression (fastest, uses more disk)
- `yes` - System default (gzip)
- `gzip` - Explicit gzip compression
- `bzip2` - Better compression, slower

```yaml
cache:
  compression: gzip  # Compress build artifacts
```

### Task Inheritance

Cache configuration supports inheritance:
- Derived tasks can override `enabled` and `compression`
- Derived tasks **append** to `hash` expressions (not replace)

```yaml
tasks:
  - name: base_build
    cache:
      enabled: true
      hash:
        - shell("gcc --version")
  
  - name: optimized_build
    uses: base_build
    cache:
      compression: gzip  # Override compression
      hash:
        - env.OPT_FLAGS  # Appends to base hash list
```

## Expression Enhancements

### shell() Built-in Function

Execute shell commands in expressions:

```yaml
cache:
  hash:
    - shell("gcc --version")
    - shell("git rev-parse HEAD")
```

**Error handling:** If command fails, the command, location, and output are reported as errors.

### Nested Variable References

Variables can be nested:

```yaml
cache:
  hash:
    - shell("${{ env.CC }} --version")
    - shell("${{ shell('which gcc') }} -v")
```

### Default Values

Provide fallback values:

```yaml
cache:
  hash:
    - env.CC:-gcc              # Use $CC or default to "gcc"
    - env.CFLAGS:-"-O2 -Wall"  # Default CFLAGS
```

Syntax: `variable:-default_value`

## Hash Providers

Hash providers determine how different file types are hashed.

### Default Hash Provider

The built-in `DefaultHashProvider` computes MD5 hashes of:
- File contents (all files in fileset)
- Fileset metadata (filetype, defines, params, incdirs)

### Extensibility

DV Flow's hash provider system is pluggable:

```python
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.hash_provider import HashProvider

class MyHashProvider:
    def supports(self, filetype: str) -> bool:
        return filetype == "myCustomType"
    
    async def compute_hash(self, fileset, rundir):
        # Custom hashing logic
        return md5_hash_string

# Register with priority (higher = checked first)
ExtRgy.inst().register_hash_provider(MyHashProvider(), priority=10)
```

**Future:** Specialized providers for SystemVerilog (including preprocessor files) and C/C++ (including headers).

## Cache Configuration

### Environment Variable: DV_FLOW_CACHE

DFM uses the `DV_FLOW_CACHE` environment variable to configure caching.

**Single directory cache:**
```bash
export DV_FLOW_CACHE=/path/to/cache
```

**Multi-provider config file:**
```bash
export DV_FLOW_CACHE=/path/to/cache-config.yaml
```

Config file format:
```yaml
caches:
  - type: directory
    path: ~/.cache/dv-flow
    writable: true
    
  - type: directory
    path: /shared/readonly/cache
    writable: false
```

### Cache Provider Priority

When multiple providers are configured:
- **Read:** First provider with matching entry wins
- **Write:** All writable providers store the entry

This enables tiered caching (fast local + shared team cache).

### Cache Provider API

All cache providers implement:

```python
class CacheProvider(Protocol):
    async def get(self, key: str) -> Optional[CacheEntry]
    async def put(self, key: str, entry: CacheEntry) -> bool
    async def exists(self, key: str) -> bool
```

## Cache Management Commands

### dfm cache init

Initialize a cache directory:

```bash
dfm cache init <cache_dir> [--shared]
```

Options:
- `cache_dir` - Path to cache directory (created if needed)
- `--shared` - Set permissions for team access (0o2775)

Creates:
- Cache directory with parents
- `.cache_config.yaml` metadata file

### Future Commands

Planned for future versions:
- `dfm cache stats` - Show hit rate, size, entry count
- `dfm cache clean` - Remove old/unused entries
- `dfm cache verify` - Check cache integrity
- `dfm cache list` - List cached entries

## Cache Directory Structure

```
<cachedir>/
  <taskname>/
    <hash>/
      .lock              - File lock for concurrent access
      output.json        - Output template with ${{ rundir }} placeholders
      metadata.json      - Creation time, metadata
      artifacts/         - Uncompressed artifacts (or)
      artifacts.tar.gz   - Gzip compressed artifacts (or)
      artifacts.tar.bz2  - Bzip2 compressed artifacts
```

### Concurrent Access

Cache uses file-based locking (`fcntl`) to handle concurrent access:
- **Shared locks** for reading (multiple readers allowed)
- **Exclusive locks** for writing (single writer)
- **NFS-compatible** (NFS v4+ required)

## Path Portability

Cached entries must work across different machines and users.

### Output Validation

Before caching, output filesets are validated:
- **Requirement:** All fileset paths must be within `rundir`
- **If violated:** Warning issued, task not cached

### Path Templates

Absolute paths are converted to templates:
```yaml
# Before (machine-specific)
basedir: /home/user/project/rundir/build

# After (portable)
basedir: ${{ rundir }}/build
```

On cache restore, templates are expanded to actual rundir.

## Performance Characteristics

### Cache Hit

Typical speedup:
- **Compilation tasks:** 10-100x faster
- **Large artifact extraction:** 2-10x faster than rebuild
- **No-artifact tasks:** >1000x faster (instant return)

### Cache Miss Overhead

Minimal impact:
- Cache key computation: ~1-5ms (depends on input file count)
- Cache lookup: ~1-10ms (depends on provider)
- Total overhead: <20ms for typical tasks

### Compression Trade-offs

| Compression | Speed | Disk Usage | Best For |
|-------------|-------|------------|----------|
| None | Fastest | High | Fast local disk, small artifacts |
| Gzip | Medium | Medium | Good balance, default choice |
| Bzip2 | Slow | Low | Large artifacts, slow network |

## Troubleshooting

### Cache Not Working

**Check environment:**
```bash
echo $DV_FLOW_CACHE
# Should point to cache directory
```

**Check task config:**
```yaml
cache:
  enabled: true  # Make sure it's enabled
```

**Check logs:**
```bash
dfm run --log-level DEBUG my_task
# Look for "Cache hit" or "Stored in cache" messages
```

### Paths Outside Rundir

**Problem:** Warning: "outputs reference paths outside rundir"

**Cause:** Task produces filesets pointing outside rundir

**Solution:** Ensure all outputs are within rundir:
```yaml
# Bad - absolute path outside rundir
run: gcc -o /tmp/output main.c

# Good - relative to rundir
run: gcc -o output main.c
```

### Cache Misses Expected Hits

**Check hash expressions:**
```yaml
cache:
  hash:
    - shell("gcc --version")  # Make sure command is deterministic
```

**Avoid non-deterministic inputs:**
- Timestamps in hash expressions
- Random values
- Absolute paths that change

### Permission Issues (Shared Cache)

**Problem:** Cannot write to shared cache

**Solution:**
```bash
# Set group ownership
chgrp -R myteam /shared/cache

# Set permissions
chmod -R 2775 /shared/cache

# Verify
ls -la /shared/cache
```

## Best Practices

### 1. Use Shared Caches for Teams

```bash
# Set up once
dfm cache init /shared/team/cache --shared

# All team members
export DV_FLOW_CACHE=/shared/team/cache
```

### 2. Hash Tool Versions

```yaml
cache:
  hash:
    - shell("${{ env.CC:-gcc }} --version")
    - shell("make --version")
```

### 3. Use Compression Wisely

```yaml
# Large build artifacts
cache:
  compression: gzip

# Small generated files
cache:
  compression: no
```

### 4. Tiered Caching

```yaml
# cache-config.yaml
caches:
  - path: ~/.cache/dv-flow  # Fast local
    writable: true
  - path: /shared/cache      # Shared team
    writable: true
```

### 5. Disable for Non-Deterministic Tasks

```yaml
tasks:
  - name: generate_timestamp
    run: date > timestamp.txt
    cache: false  # Output always changes
```

## Migration Guide

### Adding Caching to Existing Flow

1. **Initialize cache:**
   ```bash
   dfm cache init ~/.cache/dv-flow
   export DV_FLOW_CACHE=~/.cache/dv-flow
   ```

2. **Enable per task:**
   ```yaml
   # Start with long-running tasks
   - name: compile
     cache: true
   ```

3. **Add hash expressions as needed:**
   ```yaml
   - name: compile
     cache:
       hash:
         - shell("gcc --version")
   ```

4. **Monitor cache usage:**
   ```bash
   du -sh $DV_FLOW_CACHE
   ```

### Disabling Caching

Temporarily:
```bash
unset DV_FLOW_CACHE
```

Permanently:
```yaml
tasks:
  - name: my_task
    cache: false
```

## Implementation Details

### Cache Entry Format

```json
{
  "key": "taskname:abc123...",
  "output_template": {
    "output": [
      {
        "type": "std.FileSet",
        "basedir": "${{ rundir }}/build",
        "files": ["output.o"]
      }
    ]
  },
  "artifacts_path": "artifacts.tar.gz",
  "compression": "gzip",
  "created": "2026-01-17T20:00:00",
  "metadata": {
    "task": "compile"
  }
}
```

### Hash Computation Algorithm

```python
md5_hash = MD5()
md5_hash.update(task_name)
md5_hash.update(fileset_hashes)
md5_hash.update(json(params))
md5_hash.update(extra_hash_expressions)
cache_key = f"{task_name}:{md5_hash.hexdigest()}"
```

## See Also

- [Quick Start Guide](quickstart.rst) - Getting started with DV Flow
- [Task Reference](reference/tasks.rst) - Complete task definition reference
- [Command Reference](cmdref.rst) - All DFM commands

## Limitations and Future Work

### Current Limitations

- No remote cache support (S3, HTTP, etc.)
- No cache statistics/analytics
- No automatic cache cleanup
- No specialized hash providers for SV/C files yet

### Planned Enhancements

- Remote cache providers (S3, GCS, HTTP)
- `dfm cache stats` command
- `dfm cache clean` with policies
- SVHashProvider for SystemVerilog includes
- CHashProvider for C/C++ headers
- Cache warming (pre-populate from CI)

## Support

For issues, questions, or contributions:
- GitHub Issues: [dv-flow-mgr issues](https://github.com/yourorg/dv-flow-mgr/issues)
- Documentation: [Online docs](https://dv-flow-mgr.readthedocs.io)


