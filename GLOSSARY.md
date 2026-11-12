# Sherman L Watch App

Vocabulary for the owner's custom riding application and its relationship to the watch and electric unicycle.

## Language

**Wheel**:
The electric unicycle supplying riding information to the watch; in this project, the owner's Leaperkim Sherman L.
_Avoid_: Using Veteran or Leaperkim alone when a claim is specific to the Sherman L.

**Watch**:
The owner's dedicated wrist-worn riding device, presenting wheel information and vibration alerts through the custom Sherman L application.

**Wheel battery**:
The wheel's traction battery, represented on the riding dashboard by percentage and average cell voltage.

**Average cell voltage**:
The wheel battery's pack voltage divided by its number of series-connected cell groups. It is a pack-derived average, not an individual-cell reading or the weakest cell's voltage.

**Estimated wheel battery percentage**:
A voltage-based estimate of the wheel battery's charge level, distinct from a verified wheel-reported percentage or an estimate of remaining range.

**Watch battery**:
The watch's own battery, shown separately from the wheel battery on the riding dashboard.

**Direct connection**:
A connection between the watch and the wheel that does not require a phone to relay riding information.

**Riding dashboard**:
The watch view presenting speed, PWM, wheel battery, watch battery, and connection status during a ride.

**Vibration alert**:
A tactile notification delivered by the watch when a configured riding condition is met.

**EUC Watch**:
The existing community project discussed in the imported chat archive. It is a reference project distinct from the owner's custom watch application.

**Riding preset**:
A named, configurable group of wheel riding settings applied together by the rider to change riding characteristics. Its controls use the terms Dynamic assist, Pedal sensitivity and optional Pedal dip compensation.

**Preset menu**:
The watch view containing four preset slots, where pressing a configured preset requests its immediate application, including during riding.

**Preset slot**:
One of four fixed positions in the preset menu, containing a named riding preset or remaining unconfigured.

**Preset draft**:
The unsaved definition of a selected riding preset, including its name, riding values and optional-field inclusion.
_Avoid_: Treating a draft as an already saved preset.

**Preset value entry**:
The unaccepted name or percentage being entered for one preset field, separate from the preset draft.
_Avoid_: Treating an accepted value entry as a saved riding preset.

**Omitted dip**:
A preset's saved Pedal dip compensation value that is excluded when the preset is applied to the wheel.
_Avoid_: Equating omission with a zero value or a command to reset the wheel's dip.

**Wheel riding settings**:
The wheel's current riding-control values, including Pedal sensitivity, Dynamic assist and Pedal dip compensation, regardless of which device or application changed them.

**Preset editor**:
The view for editing and saving the local definition of one of the four named riding presets, independently of the wheel connection.
_Avoid_: Equating preset editing or saving with applying a preset to the wheel.

**Preset value editor**:
The view for entering one preset field's value before accepting it into the preset draft or discarding that entry.
_Avoid_: Confusing cancellation of one value entry with cancellation of the entire preset draft.

**Dynamic assist**:
The EUC World percentage control for assistance during acceleration and braking, previously called Acceleration Assist in this project's discussions.

**Pedal dip compensation**:
The EUC World percentage control for compensation of pedal dipping during dynamic maneuvers, previously shortened to Pedal Dip in this project's discussions.
_Avoid_: Confusing it with the degree-based Pedal tilt setting.

**Pedal sensitivity**:
The percentage control explicitly labelled Pedal sensitivity in the owner's EUC World screen; the matching riding-response setting is labelled Ride mode setting in the owner's LeaperKim screen.
_Avoid_: Confusing this with the degree-based Pedal tilt setting.

**Horn**:
A rider-requested sound from the wheel’s internal alarm speaker, intended to be immediately accessible from the watch.
_Avoid_: Confusing this with watch vibration alerts or a change to wheel alarm thresholds.

**Laptop application**:
The staging prototype used on the laptop to test the intended production watch experience before uploading changes to the watch.
_Avoid_: Treating visual or simulated prototype results as production watch hardware acceptance.

**Confirmed riding preset**:
A requested riding preset for which fresh wheel-originated readings confirm every included setting matches the requested value.
_Avoid_: Treating a sent command or cached setting as confirmation, or confusing wheel confirmation with a user confirmation dialog.

**Watch configuration**:
The saved riding presets and alert settings available to the watch independently of a laptop or phone.
_Avoid_: Including live wheel readings, pending wheel commands or wheel confirmation in this term.

**Controller lease**:
The laptop application's grant letting one browser at a time act on it. It lapses after a period without that browser's activity, which cancels the preset draft and releases the side button; other browsers view only.
_Avoid_: Treating a viewing browser, or a request carrying an earlier session or a repeated request identity, as a new action.

**Wheel simulator**:
A controllable stand-in for the Sherman L used to exercise riding information, control responses, and failure scenarios without the physical wheel.

**Wheel recording**:
A timestamped capture of wheel communication used to replay observed behavior, distinct from a live connection to the wheel.
