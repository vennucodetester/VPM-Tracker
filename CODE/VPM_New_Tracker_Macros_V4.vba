VBA MACROS FOR VPM_NEW_TRACKER.XLSM - VERSION 4
========================================

UPDATES IN V4:
- Added "Fix Outline Grouping" button (one-time fix for existing data)
- Enhanced delete task error handling
- Fixed outline grouping for all rows based on Level column
- Simplified right-click menu

INSTALLATION INSTRUCTIONS:
1. Open VPM_New_Tracker.xlsx or .xlsm in Excel
2. Press Alt+F11 to open VBA Editor
3. In the left panel, double-click "Sheet1 (Tasks)" under "Microsoft Excel Objects"
4. DELETE ALL EXISTING CODE in the Sheet1 window
5. Copy and paste PART 1: SHEET CODE (below) into the code window
6. In the left panel, look for "Module1" under "Modules"
   - If Module1 exists: Double-click it and DELETE ALL EXISTING CODE
   - If Module1 doesn't exist: Insert → Module (creates Module1)
7. Copy and paste PART 2: MODULE CODE (below) into Module1
8. Close VBA Editor (Alt+Q)
9. File → Save

IMPORTANT - RUN THIS ONCE AFTER INSTALLATION:
1. Right-click anywhere in the sheet
2. Select "Fix Outline Grouping"
3. This will set outline levels on all existing rows
4. You only need to run this once

========================================
PART 1: SHEET CODE
========================================
Paste this into "Sheet1 (Tasks)" code window:

'=========================================
' PART 1A: Module-level variables
'=========================================
Private lastExpandedRow As Long
Private Const COL_TASK_NAME As Long = 1
Private Const COL_START_DATE As Long = 2
Private Const COL_END_DATE As Long = 3
Private Const COL_DURATION As Long = 4
Private Const COL_STATUS As Long = 5
Private Const COL_OWNER As Long = 6
Private Const COL_NOTES As Long = 7
Private Const COL_ID As Long = 8
Private Const COL_LEVEL As Long = 9
Private Const COL_PARENT_ID As Long = 10
Private Const COL_DATES_LOCKED As Long = 11
Private Const COL_OWNER_LIST As Long = 13

'=========================================
' PART 1B: Smart Notes - Double-Click Handler
'=========================================
Private Sub Worksheet_BeforeDoubleClick(ByVal Target As Range, Cancel As Boolean)
    ' Auto-add date to Notes column when double-clicked

    ' Only trigger for Notes column (Column G)
    If Target.Column = COL_NOTES And Target.Row >= 2 Then
        Cancel = True

        ' Store current row for later collapsing
        lastExpandedRow = Target.Row

        ' Format current date as [MM/DD]
        Dim dateStr As String
        dateStr = "[" & Format(Date, "mm/dd") & "]"

        ' Get existing text
        Dim currentText As String
        currentText = Target.Value

        ' Prepend new date entry at the top
        Dim newText As String
        If Len(currentText) > 0 Then
            newText = dateStr & ": " & vbLf & currentText
        Else
            newText = dateStr & ": "
        End If

        ' Update cell
        Target.Value = newText

        ' Expand row to show all text
        Target.EntireRow.AutoFit

        ' Enter edit mode and position cursor after colon
        Target.Select
        Application.SendKeys "{F2}"
        Application.SendKeys "{HOME}"
        Application.SendKeys "{END}"
        Application.SendKeys "{LEFT " & Len(vbLf & currentText) & "}"
    End If
End Sub

'=========================================
' PART 1C: Auto-Collapse Row Handler
'=========================================
Private Sub Worksheet_SelectionChange(ByVal Target As Range)
    ' Collapse previously expanded row when moving to different row

    Application.EnableEvents = False
    On Error GoTo ErrorHandler

    ' Check if we're on a different row than the last expanded one
    If lastExpandedRow > 0 And Target.Row <> lastExpandedRow Then
        ' Reset row height to standard
        Rows(lastExpandedRow).RowHeight = 15
        lastExpandedRow = 0
    End If

ErrorHandler:
    Application.EnableEvents = True
End Sub

'=========================================
' PART 1D: Worksheet Change Handler (Date Rollup & Validation)
'=========================================
Private Sub Worksheet_Change(ByVal Target As Range)
    ' Trigger timeline rollup when dates change
    ' Validate child dates against parent hard dates

    Application.EnableEvents = False
    On Error GoTo ErrorHandler

    ' Check if Start Date or End Date column changed (Columns B or C)
    If Target.Column = COL_START_DATE Or Target.Column = COL_END_DATE Then
        If Target.Row >= 2 Then
            ' Validate date format
            If Target.Value <> "" And Not IsEmpty(Target.Value) Then
                If Not IsDate(Target.Value) Then
                    MsgBox "Invalid date format. Please use MM/DD/YYYY", vbExclamation, "Invalid Date"
                    Target.Value = ""
                    GoTo ErrorHandler
                Else
                    Target.Value = Format(Target.Value, "mm/dd/yyyy")
                    Target.NumberFormat = "mm/dd/yyyy"
                End If
            End If

            ' Check if this task violates parent hard dates
            Call ValidateChildDatesAgainstParent(Target.Row)

            ' Trigger timeline rollup (recalculate parent dates)
            Call RecalculateParentDates
        End If
    End If

    ' Status dropdown validation (Column E)
    If Target.Column = COL_STATUS And Target.Row >= 2 Then
        Dim validStatuses As Variant
        validStatuses = Array("Not Started", "In Progress", "Completed", "Delayed")

        Dim isValid As Boolean
        isValid = False

        Dim status As Variant
        For Each status In validStatuses
            If Target.Value = status Then
                isValid = True
                Exit For
            End If
        Next status

        If Not isValid And Target.Value <> "" Then
            MsgBox "Invalid status. Please select from dropdown.", vbExclamation, "Invalid Status"
            Target.Value = "Not Started"
        End If
    End If

ErrorHandler:
    Application.EnableEvents = True
End Sub

'=========================================
' PART 1E: Right-Click Context Menu
'=========================================
Private Sub Worksheet_BeforeRightClick(ByVal Target As Range, Cancel As Boolean)
    ' Add custom context menu options

    If Target.Row < 2 Then Exit Sub

    ' Clear existing custom menu items
    On Error Resume Next
    Dim ctrl As Object
    For Each ctrl In Application.CommandBars("Cell").Controls
        If ctrl.Caption = "Add Subtask" Or _
           ctrl.Caption = "Delete Task" Or _
           ctrl.Caption = "Lock Dates" Or _
           ctrl.Caption = "Unlock Dates" Or _
           ctrl.Caption = "Edit Owner List" Or _
           ctrl.Caption = "Fix Outline Grouping" Or _
           ctrl.Caption = "Apply Leaf/Parent Colors" Or _
           ctrl.Caption = "Refresh Colors" Or _
           ctrl.Caption = "-" Then
            ctrl.Delete
        End If
    Next ctrl
    On Error GoTo 0

    ' Add custom menu items
    With Application.CommandBars("Cell")
        ' Fix Outline Grouping (one-time setup)
        .Controls.Add Type:=msoControlButton, before:=1
        .Controls(1).Caption = "Fix Outline Grouping"
        .Controls(1).OnAction = "FixOutlineGrouping"
        .Controls(1).FaceId = 2

        ' Apply Leaf/Parent Colors (one-time setup)
        .Controls.Add Type:=msoControlButton, before:=2
        .Controls(2).Caption = "Apply Leaf/Parent Colors"
        .Controls(2).OnAction = "ApplyLeafParentColors"
        .Controls(2).FaceId = 3

        ' Refresh Colors (fix colors if broken)
        .Controls.Add Type:=msoControlButton, before:=3
        .Controls(3).Caption = "Refresh Colors"
        .Controls(3).OnAction = "RefreshAllColors"
        .Controls(3).FaceId = 10

        ' Separator
        .Controls.Add Type:=msoControlButton, before:=4
        .Controls(4).Caption = "-"
        .Controls(4).BeginGroup = True

        ' Task operations
        .Controls.Add Type:=msoControlButton, before:=5
        .Controls(5).Caption = "Add Subtask"
        .Controls(5).OnAction = "AddSubtaskButton"

        .Controls.Add Type:=msoControlButton, before:=6
        .Controls(6).Caption = "Delete Task"
        .Controls(6).OnAction = "DeleteTaskButton"

        ' Separator
        .Controls.Add Type:=msoControlButton, before:=7
        .Controls(7).Caption = "-"
        .Controls(7).BeginGroup = True

        ' Lock/Unlock dates
        Dim datesLocked As String
        datesLocked = UCase(Trim(Cells(Target.Row, COL_DATES_LOCKED).Value))

        If datesLocked = "TRUE" Then
            .Controls.Add Type:=msoControlButton, before:=8
            .Controls(8).Caption = "Unlock Dates"
            .Controls(8).OnAction = "UnlockDatesButton"
        Else
            If Not IsEmpty(Cells(Target.Row, COL_START_DATE).Value) And _
               Not IsEmpty(Cells(Target.Row, COL_END_DATE).Value) Then
                .Controls.Add Type:=msoControlButton, before:=8
                .Controls(8).Caption = "Lock Dates"
                .Controls(8).OnAction = "LockDatesButton"
            End If
        End If

        ' Separator
        .Controls.Add Type:=msoControlButton, before:=9
        .Controls(9).Caption = "-"
        .Controls(9).BeginGroup = True

        ' Edit Owner List
        .Controls.Add Type:=msoControlButton, before:=10
        .Controls(10).Caption = "Edit Owner List"
        .Controls(10).OnAction = "EditOwnerListButton"
    End With
End Sub


========================================
PART 2: MODULE CODE
========================================
Paste this into Module1:

'=========================================
' CONSTANTS (must match Sheet code)
'=========================================
Private Const COL_TASK_NAME As Long = 1
Private Const COL_START_DATE As Long = 2
Private Const COL_END_DATE As Long = 3
Private Const COL_DURATION As Long = 4
Private Const COL_STATUS As Long = 5
Private Const COL_OWNER As Long = 6
Private Const COL_NOTES As Long = 7
Private Const COL_ID As Long = 8
Private Const COL_LEVEL As Long = 9
Private Const COL_PARENT_ID As Long = 10
Private Const COL_DATES_LOCKED As Long = 11
Private Const COL_OWNER_LIST As Long = 13

'=========================================
' MACRO 0: Fix Outline Grouping (ONE-TIME SETUP)
'=========================================
Sub FixOutlineGrouping()
    ' Fix outline levels for all existing rows
    ' Run this ONCE after installing macros

    On Error GoTo ErrorHandler

    ' Set summary row position (plus signs at top/parent level)
    ActiveSheet.Outline.SummaryRow = xlAbove

    ' Find last row
    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    ' Loop through all rows and set OutlineLevel based on Level column
    Dim i As Long
    For i = 2 To lastRow
        Dim taskLevel As Variant
        taskLevel = Cells(i, COL_LEVEL).Value

        If IsNumeric(taskLevel) And taskLevel > 0 Then
            Rows(i).OutlineLevel = CLng(taskLevel)
        End If
    Next i

    MsgBox "Outline grouping fixed!" & vbCrLf & vbCrLf & _
           "Plus signs should now appear on parent rows." & vbCrLf & _
           "Click + to expand, - to collapse.", vbInformation, "Success"
    Exit Sub

ErrorHandler:
    MsgBox "Error fixing outline: " & Err.Description, vbCritical
End Sub

'=========================================
' MACRO 0B: Refresh All Colors (DYNAMIC)
'=========================================
Sub RefreshAllColors()
    ' Dynamically update colors based on actual parent-child relationships
    ' Call this after any add/delete/modify operation

    On Error GoTo ErrorHandler

    Application.ScreenUpdating = False

    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    ' Loop through all data rows
    Dim i As Long
    For i = 2 To lastRow
        ' Get task properties
        Dim taskID As Variant
        Dim endDate As Variant
        Dim statusVal As String

        taskID = Cells(i, COL_ID).Value
        endDate = Cells(i, COL_END_DATE).Value
        statusVal = Trim(Cells(i, COL_STATUS).Value)

        ' Reset to default (no color)
        Cells(i, COL_TASK_NAME).Resize(1, 7).Interior.ColorIndex = xlNone
        Cells(i, COL_TASK_NAME).Resize(1, 7).Font.Color = RGB(0, 0, 0)
        Cells(i, COL_TASK_NAME).Resize(1, 7).Font.Bold = False

        ' PRIORITY 1: Overdue (Red)
        If IsDate(endDate) And statusVal <> "Completed" Then
            If CDate(endDate) < Date Then
                Cells(i, COL_TASK_NAME).Resize(1, 7).Interior.Color = RGB(255, 199, 206)
                Cells(i, COL_TASK_NAME).Resize(1, 7).Font.Color = RGB(156, 0, 6)
                Cells(i, COL_TASK_NAME).Resize(1, 7).Font.Bold = True
                GoTo NextRow
            End If
        End If

        ' PRIORITY 2: Completed (Green)
        If statusVal = "Completed" Then
            Cells(i, COL_TASK_NAME).Resize(1, 7).Interior.Color = RGB(198, 239, 206)
            Cells(i, COL_TASK_NAME).Resize(1, 7).Font.Color = RGB(0, 97, 0)
            GoTo NextRow
        End If

        ' PRIORITY 3 & 4: Leaf vs Parent (Orange vs Gray)
        If IsNumeric(taskID) Then
            Dim childCount As Long
            childCount = CountChildren(CLng(taskID))

            If childCount = 0 Then
                ' Leaf task (no children) - Light Orange
                Cells(i, COL_TASK_NAME).Resize(1, 7).Interior.Color = RGB(255, 214, 153)
            Else
                ' Parent task (has children) - Light Gray
                Cells(i, COL_TASK_NAME).Resize(1, 7).Interior.Color = RGB(242, 242, 242)
            End If
        End If

NextRow:
    Next i

    Application.ScreenUpdating = True
    Exit Sub

ErrorHandler:
    Application.ScreenUpdating = True
    MsgBox "Error refreshing colors: " & Err.Description, vbCritical
End Sub

'=========================================
' MACRO 0C: Apply Leaf/Parent Colors (ONE-TIME SETUP)
'=========================================
Sub ApplyLeafParentColors()
    ' Initial setup - clears old conditional formatting and applies dynamic colors

    On Error GoTo ErrorHandler

    Dim response As VbMsgBoxResult
    response = MsgBox("This will switch to dynamic coloring." & vbCrLf & vbCrLf & _
                      "Color scheme:" & vbCrLf & _
                      "- Red = Overdue" & vbCrLf & _
                      "- Green = Completed" & vbCrLf & _
                      "- Light Orange = Leaf tasks (action items)" & vbCrLf & _
                      "- Light Gray = Parent tasks (containers)" & vbCrLf & vbCrLf & _
                      "Continue?", vbYesNo + vbQuestion, "Apply Colors")

    If response = vbNo Then Exit Sub

    ' Clear existing conditional formatting
    ActiveSheet.Cells.FormatConditions.Delete

    ' Apply dynamic colors
    Call RefreshAllColors

    MsgBox "Colors applied successfully!" & vbCrLf & vbCrLf & _
           "Colors will now update automatically when you add/delete tasks.", _
           vbInformation, "Success"
    Exit Sub

ErrorHandler:
    MsgBox "Error applying colors: " & Err.Description, vbCritical
End Sub

'=========================================
' MACRO 1: Add Subtask Button
'=========================================
Sub AddSubtaskButton()
    ' Insert a child task below parent's last descendant

    On Error GoTo ErrorHandler

    Dim selectedRow As Long
    selectedRow = ActiveCell.Row

    ' Validation: Must select a task (not header)
    If selectedRow < 2 Then
        MsgBox "Please select a parent task first.", vbExclamation, "No Task Selected"
        Exit Sub
    End If

    ' Auto-clear filters to prevent corruption (will restore at end)
    Dim hadFilters As Boolean
    Dim filterRange As Range
    hadFilters = False

    If ActiveSheet.AutoFilterMode Then
        If ActiveSheet.FilterMode Then
            ' Filters are active - temporarily clear them
            hadFilters = True
            Set filterRange = ActiveSheet.AutoFilter.Range
            ActiveSheet.AutoFilterMode = False
        End If
    End If

    ' Set outline to show plus signs at TOP (parent level), not bottom
    ActiveSheet.Outline.SummaryRow = xlAbove

    ' Get parent info
    Dim parentID As Variant
    Dim parentLevel As Variant
    parentID = Cells(selectedRow, COL_ID).Value
    parentLevel = Cells(selectedRow, COL_LEVEL).Value

    ' Validate parent has ID and Level
    If IsEmpty(parentID) Or Not IsNumeric(parentID) Then
        MsgBox "Selected row has no valid ID. Cannot add subtask.", vbExclamation
        Exit Sub
    End If

    If IsEmpty(parentLevel) Or Not IsNumeric(parentLevel) Then
        MsgBox "Selected row has no valid Level. Cannot add subtask.", vbExclamation
        Exit Sub
    End If

    Dim parentIDLong As Long
    Dim parentLevelLong As Long
    parentIDLong = CLng(parentID)
    parentLevelLong = CLng(parentLevel)

    ' Ensure parent row has correct OutlineLevel set
    If Rows(selectedRow).OutlineLevel <> parentLevelLong Then
        Rows(selectedRow).OutlineLevel = parentLevelLong
    End If

    ' Find last descendant of this parent
    Dim lastDescendantRow As Long
    lastDescendantRow = FindLastDescendant(selectedRow, parentIDLong)

    ' Prompt for task name
    Dim taskName As String
    taskName = InputBox("Enter subtask name:", "Add Subtask")
    If taskName = "" Then Exit Sub

    ' Insert new row after last descendant
    Dim newRow As Long
    newRow = lastDescendantRow + 1
    Rows(newRow).Insert Shift:=xlDown, CopyOrigin:=xlFormatFromLeftOrAbove

    ' Calculate indentation using ">" symbol
    Dim indent As String
    indent = String(parentLevelLong * 2, " ") & "> "

    ' Populate new row
    Cells(newRow, COL_TASK_NAME).Value = indent & taskName
    Cells(newRow, COL_START_DATE).Value = Date
    Cells(newRow, COL_START_DATE).NumberFormat = "mm/dd/yyyy"
    Cells(newRow, COL_END_DATE).Value = Date + 7
    Cells(newRow, COL_END_DATE).NumberFormat = "mm/dd/yyyy"
    Cells(newRow, COL_DURATION).Formula = "=C" & newRow & "-B" & newRow
    Cells(newRow, COL_STATUS).Value = "Not Started"
    Cells(newRow, COL_OWNER).Value = ""
    Cells(newRow, COL_NOTES).Value = ""
    Cells(newRow, COL_NOTES).WrapText = True
    Cells(newRow, COL_ID).Value = GetNextID()
    Cells(newRow, COL_LEVEL).Value = parentLevelLong + 1
    Cells(newRow, COL_PARENT_ID).Value = parentIDLong
    Cells(newRow, COL_DATES_LOCKED).Value = "FALSE"

    ' Set row height
    Rows(newRow).RowHeight = 15

    ' Set outline level correctly for Excel grouping
    Rows(newRow).OutlineLevel = parentLevelLong + 1

    ' Select new task name cell for editing
    Cells(newRow, COL_TASK_NAME).Select

    ' Trigger date rollup and color refresh
    Application.EnableEvents = False
    Call RecalculateParentDates
    Call RefreshAllColors
    Application.EnableEvents = True

    ' Restore filters if they were active
    If hadFilters Then
        filterRange.AutoFilter
    End If

    Exit Sub

ErrorHandler:
    ' Restore filters even on error
    If hadFilters Then
        On Error Resume Next
        filterRange.AutoFilter
        On Error GoTo 0
    End If
    MsgBox "Error adding subtask: " & Err.Description, vbCritical
    Application.EnableEvents = True
End Sub

'=========================================
' MACRO 2: Delete Task Button
'=========================================
Sub DeleteTaskButton()
    ' Delete selected task with option to delete or promote children

    On Error GoTo ErrorHandler

    Dim selectedRow As Long
    selectedRow = ActiveCell.Row

    If selectedRow < 2 Then
        MsgBox "Please select a task to delete.", vbExclamation, "No Task Selected"
        Exit Sub
    End If

    ' Auto-clear filters to prevent corruption (will restore at end)
    Dim hadFilters As Boolean
    Dim filterRange As Range
    hadFilters = False

    If ActiveSheet.AutoFilterMode Then
        If ActiveSheet.FilterMode Then
            ' Filters are active - temporarily clear them
            hadFilters = True
            Set filterRange = ActiveSheet.AutoFilter.Range
            ActiveSheet.AutoFilterMode = False
        End If
    End If

    Dim taskName As String
    taskName = Cells(selectedRow, COL_TASK_NAME).Value

    ' Validate taskID exists and is numeric
    Dim taskID As Variant
    taskID = Cells(selectedRow, COL_ID).Value

    If IsEmpty(taskID) Then
        MsgBox "This row has no task ID. Cannot delete." & vbCrLf & _
               "Only delete rows with valid task data.", vbExclamation, "No Task ID"
        Exit Sub
    End If

    If Not IsNumeric(taskID) Then
        MsgBox "Task ID is not a number: " & taskID & vbCrLf & _
               "Cannot delete this row.", vbExclamation, "Invalid Task ID"
        Exit Sub
    End If

    Dim taskIDLong As Long
    taskIDLong = CLng(taskID)

    ' Check if task has children
    Dim childCount As Long
    childCount = CountChildren(taskIDLong)

    ' Declare response once for entire procedure
    Dim response As VbMsgBoxResult

    If childCount > 0 Then
        ' Ask user what to do with children
        Dim msg As String
        msg = "This task has " & childCount & " child task(s)." & vbCrLf & vbCrLf & _
              "What would you like to do?" & vbCrLf & vbCrLf & _
              "Yes: Delete all children too" & vbCrLf & _
              "No: Promote children (move them up one level)" & vbCrLf & _
              "Cancel: Don't delete anything"

        response = MsgBox(msg, vbYesNoCancel + vbQuestion, "Delete Task with Children")

        If response = vbCancel Then
            Exit Sub
        ElseIf response = vbYes Then
            ' Delete all children recursively
            Call DeleteTaskAndChildren(selectedRow, taskIDLong)
            MsgBox "Task and all children deleted!", vbInformation
        Else ' vbNo
            ' Promote children to parent's level
            Dim taskLevel As Variant
            taskLevel = Cells(selectedRow, COL_LEVEL).Value
            If IsNumeric(taskLevel) Then
                Call PromoteChildren(taskIDLong, CLng(taskLevel))
            End If
            Rows(selectedRow).Delete Shift:=xlUp
            MsgBox "Task deleted. Children promoted!", vbInformation
        End If
    Else
        ' No children, just confirm deletion
        response = MsgBox("Delete task: " & taskName & "?", vbYesNo + vbQuestion, "Confirm Delete")

        If response = vbYes Then
            Rows(selectedRow).Delete Shift:=xlUp
            MsgBox "Task deleted!", vbInformation
        End If
    End If

    ' Recalculate dates and refresh colors
    Application.EnableEvents = False
    Call RecalculateParentDates
    Call RefreshAllColors
    Application.EnableEvents = True

    ' Restore filters if they were active
    If hadFilters Then
        filterRange.AutoFilter
    End If

    Exit Sub

ErrorHandler:
    ' Restore filters even on error
    If hadFilters Then
        On Error Resume Next
        filterRange.AutoFilter
        On Error GoTo 0
    End If
    MsgBox "Error deleting task: " & Err.Description & vbCrLf & _
           "Error number: " & Err.Number, vbCritical, "Delete Error"
    Application.EnableEvents = True
End Sub

'=========================================
' MACRO 3: Lock Dates Button
'=========================================
Sub LockDatesButton()
    ' Lock the selected task's dates (prevent auto-rollup)

    Dim selectedRow As Long
    selectedRow = ActiveCell.Row

    If selectedRow < 2 Then Exit Sub

    ' Set lock flag
    Cells(selectedRow, COL_DATES_LOCKED).Value = "TRUE"

    ' Make dates bold
    Cells(selectedRow, COL_START_DATE).Font.Bold = True
    Cells(selectedRow, COL_END_DATE).Font.Bold = True

    MsgBox "Dates locked. Auto-rollup disabled for this task.", vbInformation, "Dates Locked"
End Sub

'=========================================
' MACRO 4: Unlock Dates Button
'=========================================
Sub UnlockDatesButton()
    ' Unlock the selected task's dates (allow auto-rollup)

    Dim selectedRow As Long
    selectedRow = ActiveCell.Row

    If selectedRow < 2 Then Exit Sub

    ' Clear lock flag
    Cells(selectedRow, COL_DATES_LOCKED).Value = "FALSE"

    ' Remove bold from dates
    Cells(selectedRow, COL_START_DATE).Font.Bold = False
    Cells(selectedRow, COL_END_DATE).Font.Bold = False

    ' Recalculate dates
    Application.EnableEvents = False
    Call RecalculateParentDates
    Application.EnableEvents = True

    MsgBox "Dates unlocked. Auto-rollup enabled.", vbInformation, "Dates Unlocked"
End Sub

'=========================================
' MACRO 5: Edit Owner List Button
'=========================================
Sub EditOwnerListButton()
    ' Edit the owner list (direct edit in column M)

    ' Unhide owner list column
    Columns(COL_OWNER_LIST).Hidden = False

    ' Select first owner cell
    Cells(2, COL_OWNER_LIST).Select

    ' Show message
    MsgBox "Edit the owner names in column M (rows 2-11)." & vbCrLf & vbCrLf & _
           "When done, right-click and select 'Done Editing Owner List'.", _
           vbInformation, "Edit Owner List"

    ' Add temporary menu option to hide column again
    On Error Resume Next
    Application.CommandBars("Cell").Controls("Done Editing Owner List").Delete
    On Error GoTo 0

    With Application.CommandBars("Cell")
        .Controls.Add Type:=msoControlButton, before:=1
        .Controls(1).Caption = "Done Editing Owner List"
        .Controls(1).OnAction = "DoneEditingOwnerList"
    End With
End Sub

'=========================================
' MACRO 6: Done Editing Owner List
'=========================================
Sub DoneEditingOwnerList()
    ' Hide owner list column after editing

    Columns(COL_OWNER_LIST).Hidden = True

    ' Remove temporary menu option
    On Error Resume Next
    Application.CommandBars("Cell").Controls("Done Editing Owner List").Delete
    On Error GoTo 0

    MsgBox "Owner list updated!", vbInformation
End Sub

'=========================================
' HELPER: Find Last Descendant
'=========================================
Function FindLastDescendant(parentRow As Long, parentID As Long) As Long
    ' Find the last row that is a descendant of parentID

    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    Dim currentRow As Long
    Dim maxDescendantRow As Long
    maxDescendantRow = parentRow

    For currentRow = parentRow + 1 To lastRow
        Dim currentParentID As Variant
        currentParentID = Cells(currentRow, COL_PARENT_ID).Value

        ' Check if this row is a direct child
        If currentParentID = parentID Then
            maxDescendantRow = currentRow

            ' Recursively check if this child has descendants
            Dim childID As Variant
            childID = Cells(currentRow, COL_ID).Value

            If IsNumeric(childID) Then
                Dim childLastDesc As Long
                childLastDesc = FindLastDescendant(currentRow, CLng(childID))

                If childLastDesc > maxDescendantRow Then
                    maxDescendantRow = childLastDesc
                End If
            End If
        End If
    Next currentRow

    FindLastDescendant = maxDescendantRow
End Function

'=========================================
' HELPER: Get Next ID
'=========================================
Function GetNextID() As Long
    ' Generate next available ID

    Dim maxID As Long
    maxID = 0

    Dim i As Long
    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    For i = 2 To lastRow
        Dim currentID As Variant
        currentID = Cells(i, COL_ID).Value
        If IsNumeric(currentID) Then
            If currentID > maxID Then
                maxID = currentID
            End If
        End If
    Next i

    GetNextID = maxID + 1
End Function

'=========================================
' HELPER: Count Children
'=========================================
Function CountChildren(taskID As Long) As Long
    ' Count direct children of taskID

    CountChildren = 0

    Dim i As Long
    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    For i = 2 To lastRow
        If Cells(i, COL_PARENT_ID).Value = taskID Then
            CountChildren = CountChildren + 1
        End If
    Next i
End Function

'=========================================
' HELPER: Delete Task And Children
'=========================================
Sub DeleteTaskAndChildren(taskRow As Long, taskID As Long)
    ' Recursively delete task and all descendants

    Dim i As Long
    Dim lastRow As Long

    ' First, find and delete all children
    Do
        lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row
        For i = lastRow To 2 Step -1
            If Cells(i, COL_PARENT_ID).Value = taskID Then
                Dim childID As Variant
                childID = Cells(i, COL_ID).Value
                If IsNumeric(childID) Then
                    Call DeleteTaskAndChildren(i, CLng(childID))
                End If
            End If
        Next i
    Loop While CountChildren(taskID) > 0

    ' Then delete the task itself
    Rows(taskRow).Delete Shift:=xlUp
End Sub

'=========================================
' HELPER: Promote Children
'=========================================
Sub PromoteChildren(parentID As Long, parentLevel As Long)
    ' Move children up one level (reduce Level by 1, update Parent_ID)

    Dim i As Long
    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    ' Get grandparent ID (parent of the deleted task)
    Dim grandparentID As Variant
    For i = 2 To lastRow
        If Cells(i, COL_ID).Value = parentID Then
            grandparentID = Cells(i, COL_PARENT_ID).Value
            Exit For
        End If
    Next i

    ' Update children
    For i = 2 To lastRow
        If Cells(i, COL_PARENT_ID).Value = parentID Then
            ' Update Parent_ID
            Cells(i, COL_PARENT_ID).Value = grandparentID

            ' Update Level
            Cells(i, COL_LEVEL).Value = parentLevel

            ' Update indentation (using ">")
            Dim taskName As String
            taskName = Cells(i, COL_TASK_NAME).Value

            ' Remove old indentation
            taskName = Replace(taskName, "> ", "")
            taskName = LTrim(taskName)

            ' Add new indentation
            If parentLevel > 1 Then
                Dim indent As String
                indent = String((parentLevel - 1) * 2, " ") & "> "
                taskName = indent & taskName
            End If

            Cells(i, COL_TASK_NAME).Value = taskName

            ' Update outline level
            Rows(i).OutlineLevel = parentLevel
        End If
    Next i
End Sub

'=========================================
' HELPER: Recalculate Parent Dates (Timeline Rollup)
'=========================================
Sub RecalculateParentDates()
    ' Recalculate parent Start/End dates from children (bottom-up)
    ' Skip tasks with locked dates

    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    ' Process in reverse order (bottom-up) to handle nested hierarchies
    Dim i As Long
    For i = lastRow To 2 Step -1
        Dim taskID As Variant
        taskID = Cells(i, COL_ID).Value

        If IsNumeric(taskID) Then
            ' Check if this task has children
            If CountChildren(CLng(taskID)) > 0 Then
                ' Check if dates are locked
                Dim datesLocked As String
                datesLocked = UCase(Trim(Cells(i, COL_DATES_LOCKED).Value))

                If datesLocked <> "TRUE" Then
                    ' Calculate earliest start and latest end from children
                    Dim earliestStart As Date
                    Dim latestEnd As Date

                    Call GetChildDateRange(CLng(taskID), earliestStart, latestEnd)

                    ' Update parent dates
                    If earliestStart <> 0 Then
                        Cells(i, COL_START_DATE).Value = earliestStart
                        Cells(i, COL_START_DATE).NumberFormat = "mm/dd/yyyy"
                    End If

                    If latestEnd <> 0 Then
                        Cells(i, COL_END_DATE).Value = latestEnd
                        Cells(i, COL_END_DATE).NumberFormat = "mm/dd/yyyy"
                    End If
                End If
            End If
        End If
    Next i
End Sub

'=========================================
' HELPER: Get Child Date Range
'=========================================
Sub GetChildDateRange(parentID As Long, ByRef earliestStart As Date, ByRef latestEnd As Date)
    ' Find earliest start and latest end among all children

    earliestStart = DateSerial(9999, 12, 31)  ' Max date
    latestEnd = DateSerial(1900, 1, 1)        ' Min date

    Dim i As Long
    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    For i = 2 To lastRow
        If Cells(i, COL_PARENT_ID).Value = parentID Then
            ' Get child dates
            Dim childStart As Variant
            Dim childEnd As Variant
            childStart = Cells(i, COL_START_DATE).Value
            childEnd = Cells(i, COL_END_DATE).Value

            ' Update earliest/latest
            If IsDate(childStart) Then
                If CDate(childStart) < earliestStart Then
                    earliestStart = CDate(childStart)
                End If
            End If

            If IsDate(childEnd) Then
                If CDate(childEnd) > latestEnd Then
                    latestEnd = CDate(childEnd)
                End If
            End If
        End If
    Next i

    ' Reset to 0 if no valid dates found
    If earliestStart = DateSerial(9999, 12, 31) Then earliestStart = 0
    If latestEnd = DateSerial(1900, 1, 1) Then latestEnd = 0
End Sub

'=========================================
' HELPER: Validate Child Dates Against Parent
'=========================================
Sub ValidateChildDatesAgainstParent(childRow As Long)
    ' Check if child dates exceed parent hard dates
    ' Show warning if so

    Dim parentID As Variant
    parentID = Cells(childRow, COL_PARENT_ID).Value

    ' No parent = top-level task
    If IsEmpty(parentID) Or parentID = "" Then Exit Sub
    If Not IsNumeric(parentID) Then Exit Sub

    ' Find parent row
    Dim parentRow As Long
    parentRow = FindRowByID(CLng(parentID))
    If parentRow = 0 Then Exit Sub

    ' Check if parent dates are locked
    Dim datesLocked As String
    datesLocked = UCase(Trim(Cells(parentRow, COL_DATES_LOCKED).Value))

    If datesLocked = "TRUE" Then
        ' Get dates
        Dim parentStart As Variant
        Dim parentEnd As Variant
        Dim childStart As Variant
        Dim childEnd As Variant

        parentStart = Cells(parentRow, COL_START_DATE).Value
        parentEnd = Cells(parentRow, COL_END_DATE).Value
        childStart = Cells(childRow, COL_START_DATE).Value
        childEnd = Cells(childRow, COL_END_DATE).Value

        If IsDate(parentStart) And IsDate(parentEnd) And _
           IsDate(childStart) And IsDate(childEnd) Then

            ' Check if child exceeds parent range
            Dim violation As Boolean
            violation = False

            Dim msg As String
            msg = "WARNING: Child Task Dates Outside Parent Range" & vbCrLf & vbCrLf

            If CDate(childStart) < CDate(parentStart) Then
                msg = msg & "Child starts " & DateDiff("d", CDate(childStart), CDate(parentStart)) & _
                      " days before parent" & vbCrLf
                violation = True
            End If

            If CDate(childEnd) > CDate(parentEnd) Then
                msg = msg & "Child ends " & DateDiff("d", CDate(parentEnd), CDate(childEnd)) & _
                      " days after parent" & vbCrLf
                violation = True
            End If

            If violation Then
                msg = msg & vbCrLf & "Parent: " & Cells(parentRow, COL_TASK_NAME).Value & _
                      vbCrLf & "  (Locked: " & Format(parentStart, "mm/dd/yyyy") & " - " & _
                      Format(parentEnd, "mm/dd/yyyy") & ")" & vbCrLf & vbCrLf & _
                      "Child: " & Cells(childRow, COL_TASK_NAME).Value & _
                      vbCrLf & "  (" & Format(childStart, "mm/dd/yyyy") & " - " & _
                      Format(childEnd, "mm/dd/yyyy") & ")" & vbCrLf & vbCrLf & _
                      "What would you like to do?" & vbCrLf & vbCrLf & _
                      "Abort = Adjust child date to fit parent" & vbCrLf & _
                      "Retry = Unlock parent dates" & vbCrLf & _
                      "Ignore = Keep child date (ignore warning)"

                Dim response As VbMsgBoxResult
                response = MsgBox(msg, vbAbortRetryIgnore + vbExclamation, "Date Validation Warning")

                If response = vbAbort Then
                    ' Adjust child dates to fit parent
                    If CDate(childStart) < CDate(parentStart) Then
                        Cells(childRow, COL_START_DATE).Value = parentStart
                    End If
                    If CDate(childEnd) > CDate(parentEnd) Then
                        Cells(childRow, COL_END_DATE).Value = parentEnd
                    End If
                ElseIf response = vbRetry Then
                    ' Unlock parent dates
                    Cells(parentRow, COL_DATES_LOCKED).Value = "FALSE"
                    Cells(parentRow, COL_START_DATE).Font.Bold = False
                    Cells(parentRow, COL_END_DATE).Font.Bold = False
                    MsgBox "Parent dates unlocked.", vbInformation
                End If
                ' vbIgnore = do nothing (keep child date)
            End If
        End If
    End If
End Sub

'=========================================
' HELPER: Find Row By ID
'=========================================
Function FindRowByID(taskID As Long) As Long
    ' Find row number for given task ID

    FindRowByID = 0

    Dim i As Long
    Dim lastRow As Long
    lastRow = Cells(Rows.Count, COL_TASK_NAME).End(xlUp).Row

    For i = 2 To lastRow
        If Cells(i, COL_ID).Value = taskID Then
            FindRowByID = i
            Exit Function
        End If
    Next i
End Function


========================================
QUICK START GUIDE
========================================

1. Install macros (instructions above)

2. Right-click anywhere → "Fix Outline Grouping"
   (This fixes all existing rows - run ONCE)

3. Test:
   - Click "+" on a parent row → children expand
   - Click "-" → children collapse
   - Right-click parent → Add Subtask
   - Try deleting a task

4. Use normally:
   - Right-click menu for all operations
   - Excel +/- buttons for expand/collapse

========================================
FIXES IN V4
========================================

Issue 1: OUTLINE GROUPING
- Added "Fix Outline Grouping" button (one-time setup)
- Sets OutlineLevel on all rows based on Level column
- Plus signs now appear at parent rows (top)

Issue 2: DELETE TASK ERROR
- Added comprehensive validation
- Checks for empty/invalid taskID
- Better error messages with error number
- Error handling throughout delete process

Issue 3: RIGHT-CLICK MENU
- Improved cleanup (loops through controls)
- 2 separators may remain but menu is functional

========================================
END OF MACROS V4
========================================
