import json


def get_prompt_aes(knowledge_point):
    # context
    prefix = ""
    if knowledge_point:
        prefix = f"""
**KNOWLEDGE POINT CONTEXT:**
This educational video is designed to teach: "{knowledge_point}"

Please evaluate the video specifically in relation to how effectively it teaches this particular knowledge point. Consider whether the content, animations, and presentation approach are appropriate and effective for conveying this specific concept.

"""

    return f"""
You are an expert educational content evaluator specializing in instructional videos with synchronized presentations and animations. Please thoroughly analyze the provided educational video across five critical dimensions and provide detailed scoring.

{prefix}

**EVALUATION FRAMEWORK:**

**1. Element Layout (20 points)**
Assess the spatial arrangement and organization of visual elements:
- Clarity and readability of text/diagrams in the presentation (left side)
- Optimal positioning and sizing of animated content (right side)
- Balance between presentation and animation areas
- Appropriate use of whitespace and visual hierarchy
- Consistency in font sizes, colors, and element positioning
- Overall aesthetic appeal and professional appearance

**2. Attractiveness (20 points)**
Evaluate the visual appeal and engagement factors:
- Color scheme harmony and appropriateness for educational content
- Visual design quality and modern aesthetic
- Engaging animation styles and effects
- Creative use of visual metaphors and illustrations
- Ability to capture and maintain learner attention
- Professional presentation quality

**3. Logic Flow (20 points)**
Analyze the pedagogical structure and content progression:
- Clear introduction, development, and conclusion of concepts
- Logical sequence of information presentation
- Smooth transitions between topics and concepts
- Appropriate pacing for learning comprehension
- Coherent connection between presentation content and animations
- Progressive complexity building (scaffolding)

**4. Accuracy and Depth (20 points)**
Evaluate content quality and educational value:
- Factual correctness of all presented information
- Appropriate depth and complexity for the specific knowledge point
- Comprehensive coverage of the key concepts within the knowledge point
- Clarity of explanations and concept definitions relevant to the topic
- Effective use of examples and illustrations that support the knowledge point
- Alignment between video content and the intended learning objective
- Scientific/academic rigor appropriate for the subject matter

**5. Visual Consistency (20 points)**
Assess uniformity and coherence throughout:
- Consistent visual style across all elements
- Uniform color palette and design language
- Coherent animation styles and timing
- Consistent typography and formatting
- Smooth integration between static and animated elements
- Maintaining visual standards throughout the entire video

**SCORING INSTRUCTIONS:**
- Provide a score for each dimension (exact decimal allowed)
- Calculate overall score as sum
- Provide specific feedback for each dimension, considering the knowledge point context
- Evaluate whether the video effectively teaches the specified knowledge point
- Assess if the pedagogical approach is suitable for the subject matter
- Consider if animations and visual elements appropriately support the knowledge point

**RESPONSE FORMAT:**
MUST structure your response in the following JSON format:

{{
"element_layout": {{
    "score": [0-20],
    "feedback": "Detailed analysis of layout quality..."
}},
"attractiveness": {{
    "score": [0-20],
    "feedback": "Assessment of visual appeal..."
}},
"logic_flow": {{
    "score": [0-20],
    "feedback": "Analysis of pedagogical structure..."
}},
"accuracy_depth": {{
    "score": [0-20],
    "feedback": "Evaluation of content quality..."
}},
"visual_consistency": {{
    "score": [0-20],
    "feedback": "Assessment of visual uniformity..."
}},
"overall_score": [0-100],
"summary": "Overall assessment and key recommendations...",
"strengths": ["List of notable strengths"],
"improvements": ["List of suggested improvements"]
}}

Please analyze the video carefully and provide comprehensive, constructive feedback that will help improve future educational content creation.
"""
