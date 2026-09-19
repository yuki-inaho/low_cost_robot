# 3D Print Checklist

XL430部品の設計・印刷可否の現状は [xl430_part_completion_status.md](xl430_part_completion_status.md) を参照してください。

This document is a simple print-tracking checklist. The checkbox only means
"physically printed"; it does not mean CAD validation, slicer validation, assembly
fit, screw fit, or operation has passed.

## XL430 Mesh-Checked Investigation Package

Use this set for the current XL430 investigation output package.

The 2026-09-18 review found that the existing `elbow_to_wrist_xl430` model is not
source-equivalent: an outside rounded profile had been mistaken for a bore.
Existing files under `outputs/parts` and `outputs/print` may predate that finding.
Mesh-printability results alone do not validate those files for assembly. The
revised driver blocks normal XL430 export and labels optional diagnostic models
`*_prototype`. See [the review](cadre_review_20260918.md).

| Printed | Part / file |
|---|---|
| [ ] | `skills/cad-reverse-parametric/outputs/print/shoulder_rotation_orig.stl` |
| [ ] | `skills/cad-reverse-parametric/outputs/print/shoulder_to_elbow_xl430.stl` |
| [ ] | `skills/cad-reverse-parametric/outputs/print/elbow_to_wrist_xl430.stl` |
| [ ] | `skills/cad-reverse-parametric/outputs/print/elbow_to_wrist_extension_xl430.stl` |
| [ ] | `skills/cad-reverse-parametric/outputs/print/gripper_static_part_xl430.stl` |
| [ ] | `skills/cad-reverse-parametric/outputs/print/gripper_moving_part_xl430_print.stl` |

## Follower Arm Original STL Set

| Printed | Part / file |
|---|---|
| [ ] | `hardware/follower/stl/arm.stl` |
| [ ] | `hardware/follower/stl/base.stl` |
| [ ] | `hardware/follower/stl/shoulder_rotation.stl` |
| [ ] | `hardware/follower/stl/shoulder_to_elbow.stl` |
| [ ] | `hardware/follower/stl/elbow_to_wrist.stl` |
| [ ] | `hardware/follower/stl/elbow_to_wrist_extension.stl` |
| [ ] | `hardware/follower/stl/gripper_static_part.stl` |
| [ ] | `hardware/follower/stl/gripper_moving_part.stl` |

## Leader Arm Original STL Set

| Printed | Part / file |
|---|---|
| [ ] | `hardware/leader/stl/leader_arm.stl` |
| [ ] | `hardware/leader/stl/base.stl` |
| [ ] | `hardware/leader/stl/shoulder_to_elbow.stl` |
| [ ] | `hardware/leader/stl/elbow_to_wrist.stl` |
| [ ] | `hardware/leader/stl/elbow_to_wrist_extension.stl` |
| [ ] | `hardware/leader/stl/gripper_handle.stl` |
| [ ] | `hardware/leader/stl/gripper_trigger.stl` |
