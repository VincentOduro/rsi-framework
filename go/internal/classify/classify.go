// Package classify implements file sensitivity classification.
// Reads .rsi/architecture.yaml and matches filepaths against glob patterns.
// Port of scripts/classify_file.py.
package classify

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// Levels in match priority order
var levels = []string{"constitution", "guarded", "open"}

// Default sensitivity when no pattern matches
const DefaultLevel = "guarded"

var (
	cache     map[string][]string
	cachePath string
	mu        sync.Mutex
)

// LoadPatterns reads and parses architecture.yaml.
// Cached after first load — same file won't be re-parsed.
func LoadPatterns(archFile string) map[string][]string {
	mu.Lock()
	defer mu.Unlock()

	if cache != nil && cachePath == archFile {
		return cache
	}

	result := parseArchitectureYAML(archFile)
	cache = result
	cachePath = archFile
	return result
}

// Classify returns the sensitivity level for a filepath.
// Returns "constitution", "guarded", or "open".
func Classify(filePath, archFile string) string {
	patterns := LoadPatterns(archFile)
	// Normalize path separators
	fp := filepath.ToSlash(filePath)

	for _, level := range levels {
		for _, pattern := range patterns[level] {
			matched, _ := filepath.Match(pattern, fp)
			if matched {
				return level
			}
			// Also check just the filename for simple patterns
			if !strings.Contains(pattern, "/") {
				matched, _ = filepath.Match(pattern, filepath.Base(fp))
				if matched {
					return level
				}
			}
			// Handle ** glob (filepath.Match doesn't support **)
			if strings.Contains(pattern, "**") {
				simplePattern := strings.ReplaceAll(pattern, "**", "*")
				// Check if the directory prefix matches
				prefix := strings.Split(pattern, "**")[0]
				if strings.HasPrefix(fp, prefix) {
					return level
				}
				matched, _ = filepath.Match(simplePattern, fp)
				if matched {
					return level
				}
			}
		}
	}
	return DefaultLevel
}

// WorkerAllowed returns true if the worker role can modify this file.
func WorkerAllowed(filePath, archFile string) bool {
	return Classify(filePath, archFile) != "constitution"
}

// parseArchitectureYAML is a simple parser matching the Python version.
// No YAML dependency needed — handles the specific structure only.
func parseArchitectureYAML(path string) map[string][]string {
	result := make(map[string][]string)

	f, err := os.Open(path)
	if err != nil {
		return result
	}
	defer f.Close()

	var currentLevel string
	inPatterns := false

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		stripped := strings.TrimSpace(line)

		// Detect sensitivity level headers
		for _, level := range levels {
			if stripped == level+":" {
				currentLevel = level
				result[currentLevel] = nil
				inPatterns = false
				break
			}
		}

		// Detect patterns list
		if stripped == "patterns:" {
			inPatterns = true
			continue
		}

		// Parse pattern entries
		if inPatterns && strings.HasPrefix(stripped, "- ") {
			pattern := strings.TrimPrefix(stripped, "- ")
			pattern = strings.Trim(pattern, "\"'")
			if pattern != "" && !strings.HasPrefix(pattern, "#") && currentLevel != "" {
				result[currentLevel] = append(result[currentLevel], pattern)
			}
		}

		// End of patterns section
		if inPatterns && stripped != "" && !strings.HasPrefix(stripped, "-") &&
			!strings.HasPrefix(stripped, "#") && stripped != "patterns:" {
			if !strings.HasPrefix(stripped, "description:") {
				inPatterns = false
			}
		}
	}

	return result
}
