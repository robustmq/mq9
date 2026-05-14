package mq9

import "fmt"

// Mq9Error is returned when the mq9 broker responds with a non-empty error field.
type Mq9Error struct {
	Message string
}

func (e *Mq9Error) Error() string {
	return fmt.Sprintf("mq9: %s", e.Message)
}

// newMq9Error wraps a server error string into an Mq9Error.
func newMq9Error(msg string) *Mq9Error {
	return &Mq9Error{Message: msg}
}
