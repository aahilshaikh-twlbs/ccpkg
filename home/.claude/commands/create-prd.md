---
description: Generate a comprehensive Product Requirements Document from conversation context
---

# Create PRD Command

Generate a comprehensive Product Requirements Document (PRD) from the current conversation context.

## Usage

```
/create-prd [output_file]
```

- Without arguments: Creates `PRD.md` in current directory
- With argument: Creates PRD at specified path (e.g., `docs/PRD.md`)

## What Gets Generated

Create a comprehensive PRD document with the following sections:

### 1. Executive Summary
- High-level overview of the product/feature
- Key objectives and goals
- Target timeline (if discussed)

### 2. Mission Statement
- Core purpose of the product/feature
- Problem being solved
- Value proposition

### 3. Target Personas
- Primary user types
- User needs and pain points
- User goals and motivations

### 4. MVP Scope
- Core features for initial release
- What's explicitly OUT of scope for MVP
- Success criteria for MVP

### 5. User Stories
Format: "As a [persona], I want to [action] so that [benefit]"
- Include acceptance criteria for each story
- Prioritize as P0 (must-have), P1 (should-have), P2 (nice-to-have)

### 6. Architecture Overview
- High-level system architecture
- Key components and their responsibilities
- Data flow diagrams (describe in text)

### 7. Technology Stack
- Frontend technologies
- Backend technologies
- Infrastructure and deployment
- Third-party services/APIs

### 8. Security Considerations
- Authentication/authorization requirements
- Data privacy requirements
- Compliance requirements (GDPR, SOC2, etc.)
- Security risks and mitigations

### 9. API Specifications
- Key API endpoints
- Request/response formats
- Authentication methods

### 10. Success Metrics
- Key Performance Indicators (KPIs)
- How success will be measured
- Target values/thresholds

### 11. Implementation Phases
- Phase breakdown with deliverables
- Dependencies between phases
- Milestones

### 12. Risk Assessment
- Technical risks
- Business risks
- Mitigation strategies

## Instructions

1. **Analyze the conversation context** to extract all product requirements, decisions, and specifications discussed
2. **Fill in each section** based on what was discussed - mark sections as "TBD" if not covered
3. **Infer reasonable defaults** where appropriate, but flag assumptions clearly
4. **Use professional PRD formatting** with clear headers, bullet points, and tables
5. **Save the document** to the specified output file

## Output Format

The PRD should be a well-formatted Markdown document that can be shared with stakeholders, developers, and designers.

## Example

```
User: /create-prd docs/marketplace-prd.md

[Claude analyzes conversation about a marketplace feature]
[Generates comprehensive PRD document]
[Saves to docs/marketplace-prd.md]
```

## Related Commands

- `/plan` - Create implementation plan from PRD
- `/tdd` - Implement features with test-driven development
