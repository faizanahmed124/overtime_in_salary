from hrms.hr.doctype.leave_type.leave_type import LeaveType


class CustomLeaveType(LeaveType):
	def validate_lwp(self):
		# Allow toggling "Is Leave Without Pay" even when allocations exist.
		# Salary slips read is_lwp from the Leave Type at calculation time.
		pass
