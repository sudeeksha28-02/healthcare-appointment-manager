import React, { useState, useEffect } from 'react';
import { fetchDoctors, createDoctor, addDoctorLeave } from '../services/api';
import { ShieldCheck, UserPlus, CalendarX, Stethoscope, Clock, CheckCircle2, AlertCircle } from 'lucide-react';

export const AdminDashboard = () => {
  const [doctors, setDoctors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  // Doctor Creation Form
  const [showAddDoctorModal, setShowAddDoctorModal] = useState(false);
  const [docFirstName, setDocFirstName] = useState('');
  const [docLastName, setDocLastName] = useState('');
  const [docEmail, setDocEmail] = useState('');
  const [docPassword, setDocPassword] = useState('');
  const [docSpecialization, setDocSpecialization] = useState('Cardiology');
  const [slotDuration, setSlotDuration] = useState(30);
  const [submittingDoc, setSubmittingDoc] = useState(false);

  // Leave Creation Form
  const [showLeaveModal, setShowLeaveModal] = useState(false);
  const [leaveDoctorId, setLeaveDoctorId] = useState('');
  const [leaveDate, setLeaveDate] = useState('');
  const [submittingLeave, setSubmittingLeave] = useState(false);

  useEffect(() => {
    loadDoctorsList();
  }, []);

  const loadDoctorsList = async () => {
    setLoading(true);
    try {
      const res = await fetchDoctors();
      setDoctors(res.data);
      if (res.data.length > 0) {
        setLeaveDoctorId(res.data[0].id);
      }
    } catch (err) {
      console.error("Error loading doctors", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDoctor = async (e) => {
    e.preventDefault();
    setSubmittingDoc(true);
    setMessage('');
    
    // Standard default working hours config
    const defaultHours = JSON.stringify({
      monday: [{ start: "09:00", end: "17:00" }],
      tuesday: [{ start: "09:00", end: "17:00" }],
      wednesday: [{ start: "09:00", end: "17:00" }],
      thursday: [{ start: "09:00", end: "17:00" }],
      friday: [{ start: "09:00", end: "17:00" }]
    });

    try {
      await createDoctor({
        email: docEmail,
        password: docPassword,
        first_name: docFirstName,
        last_name: docLastName,
        specialization: docSpecialization,
        working_hours: defaultHours,
        slot_duration_minutes: Number(slotDuration)
      });

      setShowAddDoctorModal(false);
      setMessage(`Doctor Dr. ${docLastName} successfully registered.`);
      setDocFirstName('');
      setDocLastName('');
      setDocEmail('');
      setDocPassword('');
      loadDoctorsList();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to create doctor');
    } finally {
      setSubmittingDoc(false);
    }
  };

  const handleAddLeave = async (e) => {
    e.preventDefault();
    if (!leaveDate) {
      alert("Please select a leave date.");
      return;
    }
    setSubmittingLeave(true);
    setMessage('');

    try {
      await addDoctorLeave({
        doctor_id: Number(leaveDoctorId),
        leave_date: leaveDate
      });

      setShowLeaveModal(false);
      setMessage(`Doctor leave set for ${leaveDate}. Affected appointments cancelled and patients notified.`);
      setLeaveDate('');
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to set doctor leave');
    } finally {
      setSubmittingLeave(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      
      {/* Header Banner */}
      <div className="glass-panel p-6 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-amber-400" />
            System Administration Dashboard
          </h1>
          <p className="text-sm text-slate-400 mt-1">Manage doctor accounts, working hours, and register leave cancellations</p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowLeaveModal(true)}
            className="px-4 py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-bold flex items-center gap-2 transition-all"
          >
            <CalendarX className="w-4 h-4 text-rose-400" />
            <span>Set Doctor Leave</span>
          </button>

          <button
            onClick={() => setShowAddDoctorModal(true)}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-emerald-500 hover:from-amber-400 hover:to-emerald-400 text-slate-950 text-xs font-bold flex items-center gap-2 shadow-lg shadow-amber-500/20 transition-all"
          >
            <UserPlus className="w-4 h-4" />
            <span>Register Doctor</span>
          </button>
        </div>
      </div>

      {message && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-sm flex items-center justify-between shadow-lg">
          <span>{message}</span>
          <button onClick={() => setMessage('')} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Doctors List Grid */}
      <div className="glass-panel p-6 rounded-2xl space-y-6">
        <h2 className="text-lg font-bold text-slate-200">Registered Medical Doctors</h2>

        {loading ? (
          <div className="text-center py-12 text-slate-400 text-xs">Loading doctors...</div>
        ) : doctors.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-xs">No doctors registered yet</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {doctors.map(doc => (
              <div key={doc.id} className="glass-card p-5 rounded-xl space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold text-slate-100 text-base">Dr. {doc.first_name} {doc.last_name}</h3>
                    <span className="text-xs font-semibold text-amber-400">{doc.specialization}</span>
                  </div>
                  <span className="text-[10px] font-bold bg-slate-800 text-slate-300 px-2.5 py-1 rounded-md">
                    ID #{doc.id}
                  </span>
                </div>

                <div className="text-xs text-slate-400 space-y-1">
                  <div><span className="font-semibold text-slate-300">Email:</span> {doc.email}</div>
                  <div><span className="font-semibold text-slate-300">Slot Duration:</span> {doc.slot_duration_minutes} Minutes</div>
                </div>

                <div className="pt-2 border-t border-slate-800 text-[11px] text-slate-400">
                  <span className="font-semibold text-slate-300 block mb-1">Working Schedule:</span>
                  <div className="bg-slate-950/60 p-2 rounded-lg font-mono text-[10px] text-slate-300">
                    Mon - Fri: 09:00 - 17:00 UTC
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ADD DOCTOR MODAL */}
      {showAddDoctorModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="max-w-md w-full glass-panel rounded-2xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-amber-400" />
                Register New Doctor
              </h3>
              <button onClick={() => setShowAddDoctorModal(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <form onSubmit={handleCreateDoctor} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">First Name</label>
                  <input
                    type="text"
                    required
                    value={docFirstName}
                    onChange={(e) => setDocFirstName(e.target.value)}
                    placeholder="Gregory"
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Last Name</label>
                  <input
                    type="text"
                    required
                    value={docLastName}
                    onChange={(e) => setDocLastName(e.target.value)}
                    placeholder="House"
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  value={docEmail}
                  onChange={(e) => setDocEmail(e.target.value)}
                  placeholder="house@hospital.com"
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Password</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={docPassword}
                  onChange={(e) => setDocPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Specialization</label>
                  <select
                    value={docSpecialization}
                    onChange={(e) => setDocSpecialization(e.target.value)}
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                  >
                    <option value="Cardiology">Cardiology</option>
                    <option value="Neurology">Neurology</option>
                    <option value="Pediatrics">Pediatrics</option>
                    <option value="Dermatology">Dermatology</option>
                    <option value="General Practice">General Practice</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Slot Duration</label>
                  <select
                    value={slotDuration}
                    onChange={(e) => setSlotDuration(e.target.value)}
                    className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                  >
                    <option value={15}>15 Minutes</option>
                    <option value={30}>30 Minutes</option>
                    <option value={45}>45 Minutes</option>
                    <option value={60}>60 Minutes</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddDoctorModal(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingDoc}
                  className="px-5 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs shadow-lg"
                >
                  {submittingDoc ? 'Creating...' : 'Register Doctor'}
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

      {/* DOCTOR LEAVE MODAL */}
      {showLeaveModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="max-w-md w-full glass-panel rounded-2xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-rose-400 flex items-center gap-2">
                <CalendarX className="w-5 h-5" />
                Register Doctor Leave Day
              </h3>
              <button onClick={() => setShowLeaveModal(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <form onSubmit={handleAddLeave} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Select Doctor</label>
                <select
                  value={leaveDoctorId}
                  onChange={(e) => setLeaveDoctorId(e.target.value)}
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                >
                  {doctors.map(d => (
                    <option key={d.id} value={d.id}>Dr. {d.first_name} {d.last_name} ({d.specialization})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Leave Date (Future Date)</label>
                <input
                  type="date"
                  required
                  min={new Date(Date.now() + 86400000).toISOString().split('T')[0]}
                  value={leaveDate}
                  onChange={(e) => setLeaveDate(e.target.value)}
                  className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 text-xs"
                />
              </div>

              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs space-y-1">
                <span className="font-bold block">Automatic Action Notice:</span>
                <p>Registering leave for this date will automatically cancel all HELD and CONFIRMED appointments for this doctor, queue email cancellation notifications for patients, and remove Google Calendar events.</p>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowLeaveModal(false)}
                  className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingLeave}
                  className="px-5 py-2 rounded-xl bg-rose-500 hover:bg-rose-400 text-slate-950 font-bold text-xs shadow-lg"
                >
                  {submittingLeave ? 'Processing Leave...' : 'Confirm Leave & Cancel Slots'}
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

    </div>
  );
};
