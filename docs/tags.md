# Task and Package Tags

Tags provide a flexible metadata system for categorizing and annotating tasks and packages. Tags are type-based, allowing for structured metadata with inheritance and parameter customization.

## Overview

Tags allow you to:
- Categorize tasks and packages with metadata
- Filter and query tasks based on attributes
- Attach structured information (ownership, priority, categories)
- Support both simple labels and complex key-value data

## Tag Basics

Tags are DataType instances that must derive from `std.Tag`. The base `std.Tag` type provides two standard parameters:

```yaml
types:
  - name: Tag
    with:
      category:
        type: str
        value: ""
      value:
        type: str
        value: ""
```

## Defining Custom Tag Types

Create custom tag types by inheriting from `std.Tag`:

```yaml
package:
  name: myproject
  
  types:
    # Simple tag with default category
    - name: Priority
      uses: std.Tag
      with:
        category: "priority"
        value: "medium"
    
    # Tag with additional custom parameters
    - name: Owner
      uses: std.Tag
      with:
        category: "ownership"
```

## Applying Tags

### Simple Tag Reference

Reference a tag type directly to use all its default values:

```yaml
tasks:
  - name: build
    tags: [myproject.Priority]
    run: make build
```

### Tag with Parameter Overrides

Override specific parameters using inline syntax:

```yaml
tasks:
  - name: critical_task
    tags:
      - myproject.Priority:
          value: "high"
    run: ./critical_operation.sh
```

### Multiple Tags

Apply multiple tags to a single task or package:

```yaml
tasks:
  - name: integration_test
    tags:
      - myproject.Priority:
          value: "high"
      - myproject.Owner:
          value: "qa-team"
      - std.Tag:
          category: "test-type"
          value: "integration"
    run: pytest tests/integration
```

## Package Tags

Tags can be applied at the package level:

```yaml
package:
  name: verification_suite
  tags:
    - std.Tag:
        category: "project"
        value: "core-verification"
    - std.Tag:
        category: "status"
        value: "production"
  
  tasks:
    - name: smoke_test
      run: ./smoke.sh
```

## Tag Inheritance

Tag types support inheritance, allowing you to build hierarchies:

```yaml
types:
  # Base severity tag
  - name: Severity
    uses: std.Tag
    with:
      category: "severity"
      value: "info"
  
  # Critical severity with different default
  - name: Critical
    uses: myproject.Severity
    with:
      value: "critical"
  
  # Error severity
  - name: Error
    uses: myproject.Severity
    with:
      value: "error"

tasks:
  - name: system_check
    tags: [myproject.Critical]  # inherits category="severity", value="critical"
    run: ./system_check.sh
```

## Common Tag Patterns

### Priority Tags

```yaml
types:
  - name: Priority
    uses: std.Tag
    with:
      category: "priority"
      value: "medium"

tasks:
  - name: low_priority
    tags: [myproject.Priority]  # medium by default
  
  - name: high_priority
    tags:
      - myproject.Priority:
          value: "high"
```

### Ownership Tags

```yaml
types:
  - name: Owner
    uses: std.Tag
    with:
      category: "owner"

tasks:
  - name: frontend_build
    tags:
      - myproject.Owner:
          value: "frontend-team"
  
  - name: backend_build
    tags:
      - myproject.Owner:
          value: "backend-team"
```

### Test Classification Tags

```yaml
types:
  - name: TestType
    uses: std.Tag
    with:
      category: "test-classification"

tasks:
  - name: unit_tests
    tags:
      - myproject.TestType:
          value: "unit"
  
  - name: integration_tests
    tags:
      - myproject.TestType:
          value: "integration"
  
  - name: regression_tests
    tags:
      - myproject.TestType:
          value: "regression"
```

### Environment Tags

```yaml
types:
  - name: Environment
    uses: std.Tag
    with:
      category: "deployment"

tasks:
  - name: dev_deploy
    tags:
      - myproject.Environment:
          value: "development"
  
  - name: prod_deploy
    tags:
      - myproject.Environment:
          value: "production"
```

## Variable References in Tags

Tag parameter values support variable references:

```yaml
package:
  name: myproject
  
  with:
    team_name:
      type: str
      value: "platform-team"
  
  types:
    - name: Owner
      uses: std.Tag
      with:
        category: "owner"
  
  tasks:
    - name: build
      tags:
        - myproject.Owner:
            value: "${{ team_name }}"
```

## Tag Access in Code

Tags are stored as Type instances on Task and Package objects:

```python
from dv_flow.mgr import PackageLoader

pkg = PackageLoader().load("flow.yaml")
task = pkg.task_m["myproject.build"]

# Access tags
for tag in task.tags:
    print(f"Tag: {tag.name}")
    print(f"  Category: {tag.paramT.category}")
    print(f"  Value: {tag.paramT.value}")
```

## Future Tag Features

Tags are designed to support future enhancements:
- **Task filtering**: `dv-flow run --tag=priority:high`
- **Tag queries**: Conditional execution based on tag values
- **Documentation generation**: Auto-generate docs from tags
- **Metrics and reporting**: Aggregate statistics by tag categories
- **External integrations**: Export tags for CI/CD systems

## Best Practices

1. **Use meaningful categories**: Choose descriptive category names that reflect the purpose
2. **Create tag type libraries**: Define reusable tag types at the package level
3. **Document tag types**: Add doc strings to custom tag types
4. **Consistent naming**: Use consistent conventions across projects
5. **Don't over-tag**: Apply tags purposefully, not exhaustively

## Schema

Tags are defined in the schema with flexible syntax:

```json
{
  "tags": {
    "type": "array",
    "items": {
      "oneOf": [
        {
          "type": "string",
          "description": "Type reference (e.g., 'mypkg.Tag')"
        },
        {
          "type": "object",
          "description": "Type reference with inline parameter overrides"
        }
      ]
    }
  }
}
```

## Examples

### Complete Example

```yaml
package:
  name: web_service
  tags:
    - std.Tag:
        category: "project-type"
        value: "microservice"
  
  types:
    - name: Priority
      uses: std.Tag
      with:
        category: "priority"
        value: "medium"
    
    - name: Owner
      uses: std.Tag
      with:
        category: "owner"
  
  tasks:
    - name: build
      tags:
        - web_service.Priority:
            value: "high"
        - web_service.Owner:
            value: "platform-team"
      run: npm run build
    
    - name: test
      tags:
        - web_service.Priority  # uses default "medium"
        - std.Tag:
            category: "test-type"
            value: "unit"
      run: npm test
    
    - name: deploy
      tags:
        - web_service.Priority:
            value: "critical"
        - web_service.Owner:
            value: "devops-team"
        - std.Tag:
            category: "environment"
            value: "production"
      needs: [build, test]
      run: ./deploy.sh
```
