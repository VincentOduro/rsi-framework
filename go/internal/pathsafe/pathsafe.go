// Package pathsafe handles cross-platform path normalization.
// Fixes UNC paths, WSL mounts, Windows drives — the persistent
// source of bugs in the Python/Bash version.
package pathsafe

import (
	"path/filepath"
	"strings"
)

// Normalize converts any path to a clean, forward-slash relative path
// suitable for comparison against architecture.yaml patterns.
func Normalize(path string) string {
	// Convert backslashes to forward slashes
	p := filepath.ToSlash(path)
	// Remove UNC prefix if present
	p = strings.TrimPrefix(p, "//wsl.localhost/Ubuntu")
	p = strings.TrimPrefix(p, "//wsl$/Ubuntu")
	// Remove leading slash for relative paths
	p = strings.TrimPrefix(p, "/")
	return p
}

// RelativeTo returns path relative to root, normalized with forward slashes.
func RelativeTo(path, root string) string {
	rel, err := filepath.Rel(root, path)
	if err != nil {
		return Normalize(path)
	}
	return filepath.ToSlash(rel)
}
