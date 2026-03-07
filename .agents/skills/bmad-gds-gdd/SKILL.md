---
name: bmad-gds-gdd
description: Comprehensive game design document creator. Use when the user says "lets create a game design document" or "I want to create a comprehensive GDD"
---

IT IS CRITICAL THAT YOU FOLLOW THESE STEPS - while staying in character as the current agent persona you may have loaded:

<steps CRITICAL="TRUE">
1. Always LOAD the FULL {project-root}/_bmad/core/tasks/workflow.xml
2. READ its entire contents - this is the CORE OS for EXECUTING the specific workflow-config {project-root}/_bmad/gds/workflows/2-design/gdd/workflow.yaml
3. Pass the yaml path _bmad/gds/workflows/2-design/gdd/workflow.yaml as 'workflow-config' parameter to the workflow.xml instructions
4. Follow workflow.xml instructions EXACTLY as written to process and follow the specific workflow config and its instructions
5. Save outputs after EACH section when generating any documents from templates
</steps>
