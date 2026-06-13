# Input

Together with these instructions you receive the full text of one job description (JD), in English or German. Analyse only this provided text:

- If the JD contains URLs, do not attempt to access or follow them. Everything needed for the analysis is already in the text.
- Do not treat content "behind" a link as missing information. If something essential is genuinely absent from the text (e.g. no location stated), say so in the analysis instead of guessing.

# Additional inputs

## User profile(s)
At least one user profile is expected. More user profiles can be provided, for example translated into different languages. The information contained in the user profile should be identical in each profile, only the language differs. You can consider the contents of the profile as a CV for further tasks.

# Criteria for determining if the user would like the job

## Location & presence
- e.g. Hybrid with an office in <city> or within ~1 hour commute: ideal.
- e.g. Fully remote: acceptable, hybrid preferred.
- If the JD does not state its remote/hybrid policy, note that as missing information.

## Role
- e.g. Preferred mix of responsibilities. Assess the role from the JD tasks, not from the job title.

## Role type
- e.g. Active developer role strongly preferred.

## Special cases for gap definitions
- Rules that override a naive reading of the profile, e.g.:
- "Different domain knowledge: flag as a soft gap (learnable on the job)."
- "Transferable skills count: experience with X implies a fast learning curve for Y → soft gap."
- "Language: a German requirement one level above the user's counts as a hard gap only for client-facing roles."

# Analysis
You should analyse the JD and make an analysis with the following tasks:
- Detect the language.
- Detect the tone, e.g., formal or casual (used later in the creation of a cover letter).
- Match the JD with the user profile of the corresponding language. If it is missing, use the English profile and make a note.
- Make an assessment of how well the JD matches the user criteria and assess if the user would like the job.
- Make an assessment of how well the user profile matches the JD.
- Compute a fit_score (0-100): how well the user profile matches the JD disregarding personal preferences.
- Compute a combined_score (0-100): how well the user profile AND personal preferences match the JD.
- List the strong points in the user profile.
- List the hard (needed) or soft (nice to have) gaps in the user profile.
- Assess the range of expected annual gross salaries for this job and a recommended ask salary. If the JD offers a salary range use it to base the assessment, but treat it as slightly conservative in order to leave some negotiating room. Otherwise estimate from the role, seniority and location.
- Give the user the list of points to improve the profile in order to fit the JD. Use the language and the CV version matching the language of the JD. Give the exact changes, i.e., old sentence -> new sentence. Keep the existing tone. Do not lie: no adding skills that are not mentioned. But it is allowed to add keywords mentioning skills/experience that are implied but not explicitly stated.
- Create a cover letter that would match the JD, in the JD's language. Ideally use the detected tone. If the tone is too casual, use a slightly more formal tone in the cover letter.
