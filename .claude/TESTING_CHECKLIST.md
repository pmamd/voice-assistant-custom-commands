# Testing Checklist - MANDATORY BEFORE USER INVOLVEMENT

## ⚠️ READ THIS BEFORE ASKING USER TO TEST ANYTHING

**RULE**: The user should ONLY test code that I have already thoroughly tested myself.

**RULE**: NEVER ask user to approve merging untested code to main.

## Pre-User Testing Checklist

### Phase 1: Build Verification ✅

- [ ] Connected to dev machine (192.168.86.74) via paramiko
- [ ] Checked out correct branch
- [ ] Pulled latest changes from origin
- [ ] Build completed successfully (no errors)
- [ ] Build warnings reviewed (none critical)
- [ ] Executable exists at expected path

### Phase 2: Automated Testing ✅

- [ ] Test runs for at least 30 seconds (enough time for full initialization)
- [ ] Models load successfully (Whisper + LLaMA)
- [ ] No crashes during initialization
- [ ] Main loop reaches "Start speaking or typing" message
- [ ] Expected output appears in logs (what I said would be there)

### Phase 3: Feature-Specific Verification ✅

For VAD fixes, verify:
- [ ] Wyoming connection test appears in output
- [ ] Energy output shows continuously (with `-pe` flag)
- [ ] VAD state machine logs state transitions (if possible to trigger)
- [ ] Signal handler responds to Ctrl+C (graceful shutdown)

For other features:
- [ ] Feature-specific output matches what I claimed it would do
- [ ] No obvious errors or unexpected behavior in logs

### Phase 4: Log Analysis ✅

- [ ] Read full test log (not just first/last 20 lines)
- [ ] Grep for "error", "fail", "crash" - investigate any found
- [ ] Verify expected log messages are present
- [ ] Check timing (nothing unusually slow)
- [ ] No memory leaks or resource issues visible

### Phase 5: Documentation ✅

Before asking user to test, document:
- [ ] What was changed (clear, specific)
- [ ] What was tested automatically
- [ ] What the test results showed
- [ ] What still needs manual verification (e.g., "speak into mic to test VAD")
- [ ] Known limitations or issues

## When to Involve User

### ✅ DO ask user to test when:
- All automated tests pass
- Logs show expected behavior
- I've documented what works and what needs manual testing
- I can clearly explain what the user should do and what to expect

### ❌ DON'T ask user to test when:
- Build hasn't succeeded
- Haven't run any tests yet
- Tests show errors or unexpected behavior
- "It should work" but I haven't verified
- I'm not sure what the output should look like

## Merge to Main Checklist

### ❌ NEVER merge to main without:
1. [ ] All automated tests passing
2. [ ] User manually tested and confirmed working
3. [ ] User explicitly approved the merge
4. [ ] No known bugs or regressions

### ✅ Merge to main workflow:
1. Complete all Phase 1-5 testing above
2. User tests manually and confirms it works
3. User explicitly says "merge to main" or "looks good to merge"
4. Only then: `git checkout main && git merge feature-branch`

## Example Good Testing Session

```
1. [Build on dev machine via paramiko]
   ✅ Build successful

2. [Run 60-second test]
   ✅ Models loaded
   ✅ Wyoming test appeared
   ✅ Energy output continuous
   ✅ No crashes

3. [Analyze logs]
   ✅ All expected output present
   ✅ No errors found
   ⚠️  VAD didn't trigger (no speech input - expected)

4. [Ask user to test]
   "Build successful, automated tests show:
   - Wyoming connection test ✅
   - Energy monitoring working ✅
   - Signal handler working ✅
   - VAD needs manual test (speak into mic)

   Please run ./start-assistant.sh and speak to test VAD detection."
```

## Example Bad Testing Session (DON'T DO THIS)

```
❌ "I made the changes, can you test it?"
   (No build, no tests, nothing verified)

❌ "Build succeeded, should work now. Want to test?"
   (Built but not tested - might crash immediately)

❌ "Tests look good I think. Ready to merge to main?"
   (User hasn't tested, asking to merge anyway)
```

## Recovery When I Forget

If I catch myself about to ask user to test untested code:

1. **STOP** - Don't send the message
2. Read this checklist again
3. Go back to Phase 1 and complete all checks
4. Only then proceed to user involvement

---

**Remember**: User's time is valuable. Test first, ask later.
**Remember**: Main branch should always work. Never merge untested code.
**Remember**: "It should work" is not the same as "I tested it and it works."
