---
name: bmad-gds-create-story
description: User story creation from epics. Use when the user says "lets create a user story" or "I want to create a user story"
---

IT IS CRITICAL THAT YOU FOLLOW THESE STEPS - while staying in character as the current agent persona you may have loaded:

<steps CRITICAL="TRUE">
1. Always LOAD the FULL {project-root}/_bmad/core/tasks/workflow.xml
2. READ its entire contents - this is the CORE OS for EXECUTING the specific workflow-config {project-root}/_bmad/gds/workflows/4-production/create-story/workflow.yaml
3. Pass the yaml path _bmad/gds/workflows/4-production/create-story/workflow.yaml as 'workflow-config' parameter to the workflow.xml instructions
4. Follow workflow.xml instructions EXACTLY as written to process and follow the specific workflow config and its instructions
5. Save outputs after EACH section when generating any documents from templates
</steps>
