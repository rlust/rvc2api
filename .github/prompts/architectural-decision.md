---
mode: 'agent'
description: 'Guide for making and documenting architectural decisions'
tools: ['context7']
---

# Architectural Decision Guide

This guide helps you make and document architectural decisions for the rvc2api project, ensuring they align with project goals and best practices. When completed, the architectural decision record (ADR) will be saved to `/docs/specs/adr-<decision-topic>.md` for review and implementation.

---

## 1. Decision Context

### 1.1. Problem Statement
- What architectural decision needs to be made?
- What problem are we trying to solve?
- Why is this decision important?

### 1.2. Current Architecture
- What is the current state of the relevant components?
- What constraints or limitations exist in the current system?
- Use `@context7` to analyze the affected code and understand patterns

### 1.3. Requirements and Goals
- What must this architectural decision achieve?
- What are the non-functional requirements (performance, scalability, etc.)?
- What are the long-term maintainability goals?

---

## 2. Options Analysis

### 2.1. Option 1: [Name]
- Description of the approach
- Pros:
  - [List advantages]
- Cons:
  - [List disadvantages]
- Implementation complexity: [Low/Medium/High]
- Long-term maintenance implications: [Description]

### 2.2. Option 2: [Name]
- Description of the approach
- Pros:
  - [List advantages]
- Cons:
  - [List disadvantages]
- Implementation complexity: [Low/Medium/High]
- Long-term maintenance implications: [Description]

[Add more options as needed]

---

## 3. Decision

### 3.1. Chosen Approach
- Which option is being selected?
- Why is this option the best choice?
- What were the key deciding factors?

### 3.2. Implementation Strategy
- How will this be implemented?
- What are the key components or changes needed?
- Which files/modules will be affected?

### 3.3. Migration Path
- How will we transition from the current state?
- What steps are needed to implement this change?
- Will this be a breaking change for existing code?

---

## 4. Technical Details

### 4.1. Components and Interactions
- What are the key components involved?
- How do these components interact?
- What are the data flows?

### 4.2. API Changes
- What changes to public APIs are needed?
- How will these affect consumers?

### 4.3. Data Model Changes
- What changes to data models are needed?
- How will data migrations be handled (if needed)?

---

## 5. Validation and Testing

### 5.1. Validation Approach
- How will we validate this architectural decision?
- What metrics or indicators will be used?

### 5.2. Testing Strategy
- How will the changes be tested?
- What types of tests are needed (unit, integration, performance)?

---

## 6. Risks and Mitigations

### 6.1. Identified Risks
- What risks come with this approach?
- What are the potential failure modes?

### 6.2. Mitigation Strategies
- How will each risk be mitigated?
- What fallback options exist?

---

## 7. Future Considerations

### 7.1. Future Evolution
- How might this architecture evolve in the future?
- What additional capabilities could be added?

### 7.2. Technical Debt
- What technical debt might be incurred?
- How and when should this be addressed?

---

## 8. Implementation Plan

### 8.1. Phases
- What are the implementation phases?
- What are the dependencies between phases?

### 8.2. Timeline
- What is the estimated timeline for implementation?
- What are the key milestones?

---

## 9. References and Research

### 9.1. Internal References
- What existing code or patterns should be referenced?
- What similar solutions exist within the codebase?

### 9.2. External References
- What external resources informed this decision?
- What industry best practices are being followed?

---

## Output

Once this architectural decision record is complete, save it to `/docs/specs/adr-<decision-topic>.md` where `<decision-topic>` is a kebab-case name descriptive of the decision (e.g., `adr-websocket-architecture.md` or `adr-state-management-pattern.md`). This document will serve as a record of the decision-making process and guide implementation.
