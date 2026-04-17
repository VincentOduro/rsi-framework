// Package state handles reading RSI session and preflight state files.
// Port of the state management from scripts/hooks.py.
package state

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// SessionData represents .memory/.session_timestamp
type SessionData struct {
	Timestamp string `json:"timestamp"`
	TTLHours  int    `json:"ttl_hours"`
}

// PreflightState represents .memory/.preflight_state.json
type PreflightState struct {
	ReadFiles   []string `json:"read_files"`
	EditedFiles []string `json:"edited_files"`
}

// IsSessionExpired checks if the RSI session TTL has elapsed.
func IsSessionExpired(memoryRoot string) bool {
	path := filepath.Join(memoryRoot, ".session_timestamp")
	data, err := os.ReadFile(path)
	if err != nil {
		return true
	}

	var session SessionData
	if err := json.Unmarshal(data, &session); err != nil {
		return true
	}

	ts, err := time.Parse(time.RFC3339, session.Timestamp)
	if err != nil {
		// Try ISO format with timezone
		ts, err = time.Parse("2006-01-02T15:04:05.999999+00:00", session.Timestamp)
		if err != nil {
			return true
		}
	}

	ttl := session.TTLHours
	if ttl == 0 {
		ttl = 24
	}

	return time.Since(ts) > time.Duration(ttl)*time.Hour
}

// LoadReadFiles returns the set of files recorded as read in this session.
func LoadReadFiles(memoryRoot string) map[string]bool {
	path := filepath.Join(memoryRoot, ".preflight_state.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}

	var state PreflightState
	if err := json.Unmarshal(data, &state); err != nil {
		return nil
	}

	result := make(map[string]bool, len(state.ReadFiles))
	for _, f := range state.ReadFiles {
		result[f] = true
	}
	return result
}

// RecordFileRead adds a file to the read set and writes state back.
func RecordFileRead(memoryRoot, filePath string) error {
	stateFile := filepath.Join(memoryRoot, ".preflight_state.json")
	state := loadOrCreateState(stateFile)

	// Add to read set (deduplicated)
	found := false
	for _, f := range state.ReadFiles {
		if f == filePath {
			found = true
			break
		}
	}
	if !found {
		state.ReadFiles = append(state.ReadFiles, filePath)
	}

	return saveState(stateFile, state)
}

// RecordFileEdited adds a file to the edited set.
func RecordFileEdited(memoryRoot, filePath string) error {
	stateFile := filepath.Join(memoryRoot, ".preflight_state.json")
	state := loadOrCreateState(stateFile)

	found := false
	for _, f := range state.EditedFiles {
		if f == filePath {
			found = true
			break
		}
	}
	if !found {
		state.EditedFiles = append(state.EditedFiles, filePath)
	}

	return saveState(stateFile, state)
}

// HasDelegationTrail checks if any accepted review references this file.
func HasDelegationTrail(memoryRoot, filePath string) bool {
	acceptedDir := filepath.Join(memoryRoot, "reviews", "accepted")
	entries, err := os.ReadDir(acceptedDir)
	if err != nil {
		return false
	}

	normalized := filepath.ToSlash(filePath)
	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".md") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(acceptedDir, entry.Name()))
		if err != nil {
			continue
		}
		content := filepath.ToSlash(string(data))
		if strings.Contains(content, normalized) {
			return true
		}
	}
	return false
}

// HasOverride checks if a non-expired override exists for this file.
func HasOverride(rsiRoot, filePath string) bool {
	overridesDir := filepath.Join(rsiRoot, "overrides")
	entries, err := os.ReadDir(overridesDir)
	if err != nil {
		return false
	}

	normalized := filepath.ToSlash(filePath)
	now := time.Now().UTC()

	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(overridesDir, entry.Name()))
		if err != nil {
			continue
		}

		var override struct {
			FilePath   string `json:"filepath"`
			Created    string `json:"created"`
			TTLMinutes int    `json:"ttl_minutes"`
		}
		if err := json.Unmarshal(data, &override); err != nil {
			continue
		}

		overridePath := filepath.ToSlash(override.FilePath)
		if overridePath != normalized {
			// Check wildcard
			if !strings.HasSuffix(overridePath, "*") || !strings.HasPrefix(normalized, overridePath[:len(overridePath)-1]) {
				continue
			}
		}

		created, err := time.Parse(time.RFC3339, override.Created)
		if err != nil {
			continue
		}

		ttl := override.TTLMinutes
		if ttl == 0 {
			ttl = 60
		}

		if now.Sub(created) < time.Duration(ttl)*time.Minute {
			return true
		}
	}

	return false
}

// GetRelevantFailEntries returns FAIL-index entries relevant to this file.
func GetRelevantFailEntries(memoryRoot, filePath string) []string {
	failFile := filepath.Join(memoryRoot, "technical", "FAIL-index.md")
	data, err := os.ReadFile(failFile)
	if err != nil {
		return nil
	}

	suffix := filepath.Ext(filePath)

	var all []struct {
		text     string
		mode     string
	}

	for _, line := range strings.Split(string(data), "\n") {
		trimmed := strings.TrimSpace(line)
		if !strings.HasPrefix(trimmed, "| FAIL-") {
			continue
		}
		parts := strings.Split(trimmed, "|")
		var cleaned []string
		for _, p := range parts {
			p = strings.TrimSpace(p)
			if p != "" {
				cleaned = append(cleaned, p)
			}
		}
		if len(cleaned) >= 3 {
			all = append(all, struct {
				text string
				mode string
			}{
				text: fmt.Sprintf("  %s: %s -> %s", cleaned[0], cleaned[1], cleaned[2]),
				mode: strings.ToLower(cleaned[1]),
			})
		}
	}

	// Relevance filtering (matches Python version)
	var relevant []string
	editKeywords := []string{"edit", "read", "verif", "commit", "memory"}
	pyKeywords := []string{"import", "syntax", "test"}

	for _, entry := range all {
		for _, kw := range editKeywords {
			if strings.Contains(entry.mode, kw) {
				relevant = append(relevant, entry.text)
				break
			}
		}
		if suffix == ".py" {
			for _, kw := range pyKeywords {
				if strings.Contains(entry.mode, kw) {
					relevant = append(relevant, entry.text)
					break
				}
			}
		}
		if strings.Contains(strings.ToLower(filePath), "test") && strings.Contains(entry.mode, "test") {
			relevant = append(relevant, entry.text)
		}
	}

	// Deduplicate
	seen := make(map[string]bool)
	var deduped []string
	for _, r := range relevant {
		if !seen[r] {
			seen[r] = true
			deduped = append(deduped, r)
		}
	}

	if len(deduped) > 0 && len(deduped) <= 5 {
		return deduped
	}
	if len(deduped) > 5 {
		return deduped[:5]
	}

	// Fallback: top 3 entries
	if len(all) >= 3 {
		return []string{all[0].text, all[1].text, all[2].text}
	}
	result := make([]string, len(all))
	for i, e := range all {
		result[i] = e.text
	}
	return result
}

func loadOrCreateState(path string) *PreflightState {
	data, err := os.ReadFile(path)
	if err != nil {
		return &PreflightState{}
	}
	var state PreflightState
	if err := json.Unmarshal(data, &state); err != nil {
		return &PreflightState{}
	}
	return &state
}

func saveState(path string, s *PreflightState) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}
