// Package rules implements the declarative rules engine.
// Evaluates conditions from .rsi/rules.yaml against a context map.
// Port of scripts/rules_engine.py condition evaluator.
package rules

import (
	"bufio"
	"os"
	"strings"
	"sync"
)

// Rule represents one enforcement rule from rules.yaml.
type Rule struct {
	ID        string
	Name      string
	Trigger   string
	Condition string
	Action    string // "block" or "warn"
	Message   string
}

// Result of rule evaluation.
type Result struct {
	Allowed  bool
	Messages []string
}

var (
	rulesCache []*Rule
	rulesPath  string
	mu         sync.Mutex
)

// LoadRules reads and parses rules.yaml. Cached after first load.
func LoadRules(path string) []*Rule {
	mu.Lock()
	defer mu.Unlock()

	if rulesCache != nil && rulesPath == path {
		return rulesCache
	}

	rulesCache = parseRulesYAML(path)
	rulesPath = path
	return rulesCache
}

// Evaluate checks all rules for a trigger against the given context.
func Evaluate(trigger string, ctx map[string]interface{}, rulesFile string) Result {
	rules := LoadRules(rulesFile)
	result := Result{Allowed: true}

	for _, rule := range rules {
		if rule.Trigger != trigger {
			continue
		}

		if EvalCondition(rule.Condition, ctx) {
			msg := formatMessage(rule.Message, ctx)

			if rule.Action == "block" {
				result.Messages = append(result.Messages, "[RSI "+rule.ID+"] BLOCKED: "+msg)
				result.Allowed = false
				break // First blocking rule wins
			} else if rule.Action == "warn" {
				result.Messages = append(result.Messages, "[RSI "+rule.ID+"] "+msg)
			}
		}
	}

	return result
}

// EvalCondition evaluates a boolean expression against a context map.
// Supports: and, or, not, ==, !=, in, string literals, variable lookup.
func EvalCondition(expr string, ctx map[string]interface{}) bool {
	expr = strings.TrimSpace(expr)
	if expr == "" {
		return false
	}

	// Handle 'or' (lowest precedence)
	parts := splitOutside(expr, " or ")
	if len(parts) > 1 {
		for _, p := range parts {
			if EvalCondition(p, ctx) {
				return true
			}
		}
		return false
	}

	// Handle 'and'
	parts = splitOutside(expr, " and ")
	if len(parts) > 1 {
		for _, p := range parts {
			if !EvalCondition(p, ctx) {
				return false
			}
		}
		return true
	}

	// Handle 'not'
	if strings.HasPrefix(expr, "not ") {
		return !EvalCondition(expr[4:], ctx)
	}

	// Handle parenthesized group
	if strings.HasPrefix(expr, "(") && strings.HasSuffix(expr, ")") {
		// Verify it's a complete group
		depth := 0
		complete := true
		for i, c := range expr {
			if c == '(' {
				depth++
			} else if c == ')' {
				depth--
			}
			if depth == 0 && i < len(expr)-1 {
				complete = false
				break
			}
		}
		if complete {
			return EvalCondition(expr[1:len(expr)-1], ctx)
		}
	}

	// Handle '==' comparison
	if idx := strings.Index(expr, " == "); idx >= 0 {
		left := resolve(strings.TrimSpace(expr[:idx]), ctx)
		right := resolve(strings.TrimSpace(expr[idx+4:]), ctx)
		return left == right
	}

	// Handle '!=' comparison
	if idx := strings.Index(expr, " != "); idx >= 0 {
		left := resolve(strings.TrimSpace(expr[:idx]), ctx)
		right := resolve(strings.TrimSpace(expr[idx+4:]), ctx)
		return left != right
	}

	// Handle 'in' containment
	if idx := strings.Index(expr, " in "); idx >= 0 {
		left := resolve(strings.TrimSpace(expr[:idx]), ctx)
		right := strings.TrimSpace(expr[idx+4:])

		// Right side is a tuple: ('a', 'b')
		if strings.HasPrefix(right, "(") && strings.HasSuffix(right, ")") {
			inner := right[1 : len(right)-1]
			for _, item := range strings.Split(inner, ",") {
				item = strings.TrimSpace(item)
				item = strings.Trim(item, "'\"")
				if item == left {
					return true
				}
			}
			return false
		}

		// Right side is a variable (string containment)
		rightVal := resolve(right, ctx)
		return strings.Contains(rightVal, left)
	}

	// Simple value — resolve and check truthiness
	val := resolve(expr, ctx)
	return val != "" && val != "false" && val != "0"
}

// resolve looks up a token in the context or returns a literal value.
func resolve(token string, ctx map[string]interface{}) string {
	token = strings.TrimSpace(token)

	// String literal
	if (strings.HasPrefix(token, "'") && strings.HasSuffix(token, "'")) ||
		(strings.HasPrefix(token, "\"") && strings.HasSuffix(token, "\"")) {
		return token[1 : len(token)-1]
	}

	// Boolean literals
	if strings.ToLower(token) == "true" {
		return "true"
	}
	if strings.ToLower(token) == "false" {
		return ""
	}

	// Context variable lookup
	if val, ok := ctx[token]; ok {
		switch v := val.(type) {
		case bool:
			if v {
				return "true"
			}
			return ""
		case string:
			return v
		default:
			return ""
		}
	}

	return ""
}

// splitOutside splits on separator but not inside quotes or parens.
func splitOutside(expr, sep string) []string {
	var parts []string
	depth := 0
	inQuote := false
	quoteChar := byte(0)
	var current strings.Builder
	i := 0

	for i < len(expr) {
		c := expr[i]

		if inQuote {
			current.WriteByte(c)
			if c == quoteChar {
				inQuote = false
			}
		} else if c == '\'' || c == '"' {
			inQuote = true
			quoteChar = c
			current.WriteByte(c)
		} else if c == '(' {
			depth++
			current.WriteByte(c)
		} else if c == ')' {
			depth--
			current.WriteByte(c)
		} else if depth == 0 && !inQuote && i+len(sep) <= len(expr) && expr[i:i+len(sep)] == sep {
			parts = append(parts, current.String())
			current.Reset()
			i += len(sep)
			continue
		} else {
			current.WriteByte(c)
		}

		i++
	}

	if s := current.String(); strings.TrimSpace(s) != "" {
		parts = append(parts, s)
	}

	return parts
}

// formatMessage replaces {var} placeholders with context values.
func formatMessage(msg string, ctx map[string]interface{}) string {
	for key, val := range ctx {
		placeholder := "{" + key + "}"
		if strings.Contains(msg, placeholder) {
			switch v := val.(type) {
			case string:
				msg = strings.ReplaceAll(msg, placeholder, v)
			case bool:
				if v {
					msg = strings.ReplaceAll(msg, placeholder, "true")
				} else {
					msg = strings.ReplaceAll(msg, placeholder, "false")
				}
			}
		}
	}
	return msg
}

// parseRulesYAML parses rules.yaml without a YAML dependency.
func parseRulesYAML(path string) []*Rule {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()

	var rules []*Rule
	var current *Rule

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		stripped := strings.TrimSpace(line)

		if stripped == "" || strings.HasPrefix(stripped, "#") {
			continue
		}

		if strings.HasPrefix(stripped, "- id:") {
			if current != nil {
				rules = append(rules, current)
			}
			current = &Rule{ID: strings.TrimSpace(strings.SplitN(stripped, ":", 2)[1])}
			current.ID = strings.Trim(current.ID, "\"'")
			continue
		}

		if current != nil && strings.Contains(stripped, ":") {
			key, val, _ := strings.Cut(stripped, ":")
			key = strings.TrimSpace(key)
			val = strings.TrimSpace(val)
			// Strip outer YAML quotes only
			if (strings.HasPrefix(val, "\"") && strings.HasSuffix(val, "\"")) ||
				(strings.HasPrefix(val, "'") && strings.HasSuffix(val, "'")) {
				val = val[1 : len(val)-1]
			}

			switch key {
			case "name":
				current.Name = val
			case "trigger":
				current.Trigger = val
			case "condition":
				current.Condition = val
			case "action":
				current.Action = val
			case "message":
				current.Message = val
			}
		}
	}

	if current != nil {
		rules = append(rules, current)
	}

	return rules
}
