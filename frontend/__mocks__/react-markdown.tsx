import React from 'react'

// Simple mock that renders the markdown source as plain text
const ReactMarkdown = ({ children }: { children: React.ReactNode }) => (
  <>{children}</>
)

export default ReactMarkdown
