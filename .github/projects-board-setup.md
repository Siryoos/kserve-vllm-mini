# GitHub Projects Board Setup Guide

This guide helps you set up the public roadmap as a GitHub Projects board to track development progress and community contributions.

## 1. Create New Project

1. Navigate to your repository on GitHub
2. Click **Projects** tab → **New project**
3. Choose **Board** template
4. Name: `kserve-vllm-mini Roadmap`
5. Description: `Public roadmap tracking feature development and community priorities`
6. Visibility: **Public** (important for community transparency)

## 2. Configure Board Columns

Set up these columns to match the roadmap:

### Column 1: 🟢 Good First Issues
- **Purpose**: Entry points for new contributors
- **Automation**: Auto-add issues with `good-first-issue` label

### Column 2: 🔄 In Progress
- **Purpose**: Currently being worked on
- **Automation**: Auto-add when issue assigned or PR opened

### Column 3: 🟡 Help Wanted
- **Purpose**: Community expertise needed
- **Automation**: Auto-add issues with `help-wanted` label

### Column 4: 📋 Backlog
- **Purpose**: Planned features and improvements
- **Automation**: Auto-add all new issues

### Column 5: ✅ Done
- **Purpose**: Completed features
- **Automation**: Auto-move when issue closed or PR merged

## 3. Add Roadmap Items

Create issues for each roadmap item with appropriate labels:

### Priority 1 Items (Q4 2025)
```
Title: Profile System Enhancement
Labels: enhancement, priority-1, profiles
Assignee: (leave blank for community)
Description: [Copy from ROADMAP.md]
```

### Good First Issues
```
Title: Add INT4 quantization profile
Labels: good-first-issue, profiles, quantization
Description: Create runners/profiles/quantization/int4.yaml with validation
```

## 4. Project Settings

Configure these settings for optimal community engagement:

### Field Configuration
- **Status**: Not started, In progress, Done
- **Priority**: P0 (Critical), P1 (High), P2 (Medium), P3 (Low)
- **Size**: XS, S, M, L, XL (story points)
- **Labels**: good-first-issue, help-wanted, priority-1, etc.

### Views
1. **Roadmap View**: Group by Priority, sort by Status
2. **Contributor View**: Filter by good-first-issue and help-wanted
3. **Progress View**: Group by Status, show completion percentage

### Automation Rules
- **Auto-add**: All repository issues and PRs
- **Auto-archive**: Items completed > 30 days ago
- **Auto-assign**: Issues with specific labels to team members

## 5. Link from Repository

Add this to your repository README.md:
```markdown
📈 [Public Roadmap](https://github.com/yourusername/kserve-vllm-mini/projects/1) - Track our development progress
```

## 6. Community Guidelines

Add to project description:
```markdown
## How to Contribute
- 🟢 **Good first issues**: Perfect for newcomers
- 🟡 **Help wanted**: Community expertise needed
- 📝 **RFCs**: Propose new features via issues
- 🗳️ **Voting**: +1 issues you care about

See CONTRIBUTING.md for detailed guidelines.
```

## Sample Issues to Create

Here are templates for the key roadmap items:

### Good First Issue Template
```markdown
**Title**: Add INT4 quantization profile

**Description**:
Create a new quantization profile for INT4 precision to expand our quantization testing suite.

**Tasks**:
- [ ] Create `runners/profiles/quantization/int4.yaml`
- [ ] Add validation checks for INT4 compatibility
- [ ] Test with a small model (e.g., OPT-125M)
- [ ] Document expected memory reduction in profile
- [ ] Update docs/FEATURES.md quantization matrix

**Acceptance Criteria**:
- Profile follows existing quantization profile structure
- Validation passes for INT4-compatible models
- Documentation includes performance expectations

**Labels**: good-first-issue, profiles, quantization
**Size**: S
**Priority**: P2
```

### Help Wanted Template
```markdown
**Title**: TensorRT-LLM optimization profiles

**Description**:
Create optimized profiles for TensorRT-LLM runtime with engine-specific configurations.

**Background**:
TensorRT-LLM has unique optimization patterns different from vLLM. We need community expertise to create profiles that showcase its strengths.

**Tasks**:
- [ ] Research TensorRT-LLM optimization flags
- [ ] Create engine build profiles for different model sizes
- [ ] Benchmark engine build time vs inference performance
- [ ] Document TensorRT-LLM specific deployment patterns

**Skills Needed**:
- TensorRT-LLM experience
- NVIDIA GPU architecture knowledge
- Performance optimization expertise

**Labels**: help-wanted, tensorrt, optimization
**Size**: L
**Priority**: P1
```

## 7. Maintenance

### Weekly Tasks
- Review and triage new issues
- Update progress on in-flight items
- Close completed items
- Celebrate community contributions

### Monthly Tasks
- Review roadmap priorities based on community feedback
- Update project descriptions and documentation
- Analyze contributor engagement metrics
- Plan next quarter priorities

This Projects board will become the central hub for community coordination and transparent development progress tracking.
