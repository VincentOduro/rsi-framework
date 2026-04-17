// rsi-hook — native hook binary for Claude Code.
// Replaces hooks.py with <5ms cold start.
//
// Protocol: reads JSON from stdin, prints messages to stdout,
// exits 0 (allow) or 1 (block). Same contract as hooks.py.
//
// Usage (called by .claude/settings.json):
//
//	echo '{"tool_input":{"file_path":"src/api.py"}}' | rsi-hook pre-edit
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/VincentOduro/rsi-framework/go/internal/classify"
	"github.com/VincentOduro/rsi-framework/go/internal/rules"
	"github.com/VincentOduro/rsi-framework/go/internal/state"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "Usage: rsi-hook <pre-edit|post-edit|pre-read|pre-bash>")
		os.Exit(1)
	}

	action := os.Args[1]

	if action == "--version" {
		fmt.Println("rsi-hook v2.2 (Go)")
		os.Exit(0)
	}

	// Find project root (where .rsi/ lives)
	projectRoot := findProjectRoot()
	memoryRoot := filepath.Join(projectRoot, ".memory")
	rsiRoot := filepath.Join(projectRoot, ".rsi")
	archFile := filepath.Join(rsiRoot, "architecture.yaml")
	rulesFile := filepath.Join(rsiRoot, "rules.yaml")

	// Read tool input from stdin
	toolInput := readStdin()
	filePath, _ := toolInput["file_path"].(string)

	switch action {
	case "pre-read":
		handlePreRead(memoryRoot, projectRoot, filePath)
	case "pre-edit":
		handlePreEdit(memoryRoot, projectRoot, rsiRoot, archFile, rulesFile, filePath)
	case "post-edit":
		handlePostEdit(memoryRoot, projectRoot, filePath)
	case "pre-bash":
		command, _ := toolInput["command"].(string)
		handlePreBash(rulesFile, command)
	default:
		fmt.Fprintf(os.Stderr, "Unknown action: %s\n", action)
		os.Exit(1)
	}
}

func handlePreRead(memoryRoot, projectRoot, filePath string) {
	if filePath == "" {
		return
	}
	rel := relativePath(filePath, projectRoot)
	state.RecordFileRead(memoryRoot, rel)
}

func handlePreEdit(memoryRoot, projectRoot, rsiRoot, archFile, rulesFile, filePath string) {
	if filePath == "" {
		return
	}

	rel := relativePath(filePath, projectRoot)
	relNorm := filepath.ToSlash(rel)

	// Build context for rules evaluation
	readFiles := state.LoadReadFiles(memoryRoot)
	sensitivity := classify.Classify(rel, archFile)
	role := os.Getenv("RSI_ROLE")
	if role == "" {
		role = "overlord"
	}
	minimaxKey := os.Getenv("MINIMAX_API_KEY")
	fileExists := fileExistsOnDisk(filePath)

	ctx := map[string]interface{}{
		"file":           rel,
		"file_exists":    fileExists,
		"file_was_read":  readFiles[rel] || readFiles[relNorm],
		"session_expired": state.IsSessionExpired(memoryRoot),
		"role":           role,
		"sensitivity":    sensitivity,
		"minimax_key_set": minimaxKey != "",
		"has_delegation": state.HasDelegationTrail(memoryRoot, relNorm),
		"has_override":   state.HasOverride(rsiRoot, relNorm),
	}

	// Try declarative rules engine first
	if _, err := os.Stat(rulesFile); err == nil {
		result := rules.Evaluate("pre_edit", ctx, rulesFile)
		for _, msg := range result.Messages {
			fmt.Println(msg)
		}
		if !result.Allowed {
			os.Exit(1)
		}
	} else {
		// Fallback: hardcoded rules (no rules.yaml)
		if state.IsSessionExpired(memoryRoot) {
			fmt.Println("[RSI] Session expired. Run 'python3 scripts/rsi.py init'.")
			os.Exit(1)
		}
		if fileExists && !readFiles[rel] && !readFiles[relNorm] {
			fmt.Printf("[RSI] BLOCKED: '%s' not read. Read it first.\n", rel)
			os.Exit(1)
		}
		if role == "worker" && sensitivity == "constitution" {
			fmt.Printf("[RSI] BLOCKED: '%s' is constitution-level.\n", rel)
			os.Exit(1)
		}
		if minimaxKey != "" && role != "worker" &&
			(sensitivity == "guarded" || sensitivity == "open") &&
			fileExists &&
			!state.HasDelegationTrail(memoryRoot, relNorm) &&
			!state.HasOverride(rsiRoot, relNorm) {
			fmt.Printf("[RSI] DELEGATION GATE BLOCKED: '%s' is %s-level.\n", rel, sensitivity)
			fmt.Println("[RSI] Delegate to MiniMax first.")
			os.Exit(1)
		}
	}

	// FAIL-index (non-blocking)
	entries := state.GetRelevantFailEntries(memoryRoot, filePath)
	if len(entries) > 0 {
		fmt.Printf("[RSI] FAIL-index for '%s':\n", rel)
		for _, e := range entries {
			fmt.Println(e)
		}
	}

	// Review queue warning (non-blocking)
	pendingDir := filepath.Join(memoryRoot, "reviews", "pending")
	if entries, err := os.ReadDir(pendingDir); err == nil {
		count := 0
		for _, e := range entries {
			if strings.HasSuffix(e.Name(), ".md") {
				count++
			}
		}
		if count > 0 {
			fmt.Printf("[RSI] JIDOKA: %d pending review(s).\n", count)
		}
	}
}

func handlePostEdit(memoryRoot, projectRoot, filePath string) {
	if filePath == "" {
		return
	}
	rel := relativePath(filePath, projectRoot)
	state.RecordFileEdited(memoryRoot, rel)
}

func handlePreBash(rulesFile, command string) {
	ctx := map[string]interface{}{
		"command": command,
	}

	if _, err := os.Stat(rulesFile); err == nil {
		result := rules.Evaluate("pre_bash", ctx, rulesFile)
		for _, msg := range result.Messages {
			fmt.Println(msg)
		}
		if !result.Allowed {
			os.Exit(1)
		}
	} else {
		// Fallback
		if strings.Contains(command, "git commit") && strings.Contains(command, "--no-verify") {
			fmt.Println("[RSI] BLOCKED: --no-verify bypasses quality gates.")
			os.Exit(1)
		}
	}
}

// --- Helpers ---

func readStdin() map[string]interface{} {
	data, err := io.ReadAll(os.Stdin)
	if err != nil || len(strings.TrimSpace(string(data))) == 0 {
		return map[string]interface{}{}
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		return map[string]interface{}{}
	}

	// Extract tool_input if present
	if ti, ok := raw["tool_input"]; ok {
		if tiMap, ok := ti.(map[string]interface{}); ok {
			return tiMap
		}
	}
	return raw
}

func relativePath(filePath, projectRoot string) string {
	abs, err := filepath.Abs(filePath)
	if err != nil {
		return filePath
	}
	rootAbs, err := filepath.Abs(projectRoot)
	if err != nil {
		return filePath
	}
	rel, err := filepath.Rel(rootAbs, abs)
	if err != nil {
		return filePath
	}
	return rel
}

func fileExistsOnDisk(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func findProjectRoot() string {
	// Check env var first
	if root := os.Getenv("RSI_PROJECT_ROOT"); root != "" {
		return root
	}

	// Walk up from executable location looking for .rsi/
	dir, _ := os.Getwd()
	for {
		if _, err := os.Stat(filepath.Join(dir, ".rsi")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	// Fallback to cwd
	cwd, _ := os.Getwd()
	return cwd
}
