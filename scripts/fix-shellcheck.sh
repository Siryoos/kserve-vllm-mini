#!/bin/bash

# Script to apply common shellcheck fixes automatically
# This helps with the most common shellcheck issues

set -e

fix_unquoted_variables() {
    echo "🔧 Fixing unquoted variables (SC2086)..."

    # Find files to process
    files=$(find . -name "*.sh" -type f -not -path "./.venv/*" -not -path "./docs/website/node_modules/*" -not -path "./venv/*")

    for file in $files; do
        if [[ -f "$file" ]]; then
            echo "Processing $file..."

            # Create backup
            cp "$file" "${file}.bak"

            # Apply common fixes
            # shellcheck disable=SC2016
            sed -i \
                -e 's/\$\([A-Za-z_][A-Za-z0-9_]*\)\([^A-Za-z0-9_"}\]\)]\)/"\$\1"\2/g' \
                -e 's/>> \$GITHUB_OUTPUT/>> "\$GITHUB_OUTPUT"/g' \
                -e 's/>> \$GITHUB_ENV/>> "\$GITHUB_ENV"/g' \
                "$file"

            # Check if file changed
            if ! diff -q "$file" "${file}.bak" > /dev/null 2>&1; then
                echo "  ✓ Applied fixes to $file"
            else
                echo "  - No changes needed for $file"
            fi

            # Remove backup
            rm "${file}.bak"
        fi
    done
}

fix_workflow_scripts() {
    echo "🔧 Fixing GitHub Actions workflow scripts..."

    workflows=$(find .github/workflows -name "*.yml" -o -name "*.yaml" 2>/dev/null || true)

    for workflow in $workflows; do
        if [[ -f "$workflow" ]]; then
            echo "Processing $workflow..."

            # Create backup
            cp "$workflow" "${workflow}.bak"

            # Fix common GitHub Actions shellcheck issues
            # shellcheck disable=SC2016
            sed -i \
                -e 's/\$files"$/"\$files"/g' \
                -e 's/>> \$GITHUB_OUTPUT/>> "\$GITHUB_OUTPUT"/g' \
                -e 's/>> \$GITHUB_ENV/>> "\$GITHUB_ENV"/g' \
                -e 's/! grep.*| grep.*&&[^|]*||\s*true$/if grep ... | grep ...; then\n            exit 1\n          fi/g' \
                "$workflow"

            # Check if file changed
            if ! diff -q "$workflow" "${workflow}.bak" > /dev/null 2>&1; then
                echo "  ✓ Applied fixes to $workflow"
            else
                echo "  - No changes needed for $workflow"
            fi

            # Remove backup
            rm "${workflow}.bak"
        fi
    done
}

run_shellcheck_validation() {
    echo "🧪 Running shellcheck validation..."

    if command -v shellcheck > /dev/null 2>&1; then
        # Check shell scripts
        files=$(find . -name "*.sh" -type f -not -path "./.venv/*" -not -path "./docs/website/node_modules/*" -not -path "./venv/*")

        if [[ -n "$files" ]]; then
            echo "$files" | xargs shellcheck -x || echo "Some shellcheck issues remain that require manual fixing"
        fi

        # Check workflow files with actionlint if available
        if command -v actionlint > /dev/null 2>&1; then
            echo "Running actionlint..."
            actionlint || echo "Some actionlint issues remain that require manual fixing"
        else
            echo "actionlint not found, skipping workflow validation"
        fi
    else
        echo "shellcheck not found, skipping validation"
    fi
}

main() {
    echo "🚀 Automatic ShellCheck Fix Script"
    echo "===================================="

    fix_unquoted_variables
    fix_workflow_scripts
    run_shellcheck_validation

    echo ""
    echo "✅ Automatic fixes complete!"
    echo "💡 Review changes and run 'pre-commit run --all-files' to validate"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
