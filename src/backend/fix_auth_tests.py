#!/usr/bin/env python
"""Fix authentication test assertions from 403 to 401 for no-auth tests."""

from pathlib import Path


def fix_file(filepath: Path) -> int:
    """Fix authentication assertions in a file."""
    content = filepath.read_text()
    lines = content.split('\n')
    fixed_count = 0
    in_no_auth_test = False

    for i, line in enumerate(lines):
        # Check if we're entering a no_auth or requires_auth test
        if 'def test_' in line:
            test_name = line.split('def test_')[1].split('(')[0] if 'def test_' in line else ''
            in_no_auth_test = 'no_auth' in test_name or 'requires_auth' in test_name

        # Fix the assertion if in a no_auth test
        if in_no_auth_test and 'assert resp.status_code == 403' in line:
            # Check context - don't fix if it's about permission denied (has auth but no permission)
            context = '\n'.join(lines[max(0, i-10):i+1])
            if 'permission' not in context.lower() and 'forbidden' not in context.lower():
                lines[i] = line.replace('assert resp.status_code == 403',
                                       'assert resp.status_code == 401  # Unauthorized')
                fixed_count += 1

    if fixed_count > 0:
        filepath.write_text('\n'.join(lines))

    return fixed_count

def main():
    """Main entry point."""
    backend_dir = Path(__file__).parent
    tests_dir = backend_dir / "tests"
    total_fixed = 0

    for test_file in tests_dir.glob("test_*.py"):
        fixed = fix_file(test_file)
        if fixed > 0:
            print(f"Fixed {fixed} assertions in {test_file.name}")
            total_fixed += fixed

    print(f"\nTotal fixed: {total_fixed} assertions")

if __name__ == "__main__":
    main()
