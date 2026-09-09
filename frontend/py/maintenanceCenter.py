"""
GARUDAVYUHA – Maintenance Center
Ground Control Station Predictive Maintenance Work Orders & Virtual Overhaul System
"""

import time
from datetime import datetime, timezone
from config import ENGINE_SUBSYSTEMS, ENGINE_CONFIG
from telemetryEngine import telemetryEngine


class MaintenanceCenter:
    def __init__(self, onOverhaulCompleted=None):
        self.onOverhaulCompleted = onOverhaulCompleted
        self.workOrders = []

    def getWorkOrders(self, subsystem_states):
        orders = []

        for sub_id, sub_def in ENGINE_SUBSYSTEMS.items():
            state = subsystem_states.get(sub_id, {
                "health": float(sub_def["baselineHealth"]),
                "status": "healthy"
            })
            health = round(float(state.get("health", 95)), 1)
            status = state.get("status", "healthy")
            active_fault = state.get("activeFault")

            if health < 80 or status != 'healthy':
                is_critical = (health < 45 or status == 'critical')
                order_id_suffix = str(int(time.time()))[-4:]
                orders.append({
                    "id": f"WO-{sub_id.upper()}-{order_id_suffix}",
                    "subsystemId": sub_id,
                    "componentName": sub_def["name"],
                    "health": health,
                    "status": "CRITICAL" if is_critical else "MAINTENANCE REQUIRED",
                    "priority": "HIGH PRIORITY" if is_critical else "MEDIUM PRIORITY",
                    "badgeClass": "badge-critical" if is_critical else "badge-warning",
                    "predictedIssue": active_fault["name"] if active_fault else "Subsystem Degradation & Wear Drift",
                    "recommendedAction": active_fault["recommendation"] if active_fault else sub_def["inspectionProcedure"],
                    "sparesRequired": sub_def["spares"],
                    "inspectionProcedure": sub_def["inspectionProcedure"],
                    "estServiceWindow": "Immediate Ground Inspection (< 2h)" if is_critical else "Within 25 Flight Hours",
                    "estMTTR": "2.5 - 4.0 Hours" if is_critical else "1.0 - 1.5 Hours",
                    "postServiceReadiness": 97.5,
                })

        # Default preventive routine order if everything is nominal
        if not orders:
            orders.append({
                "id": "WO-ROUTINE-50H",
                "subsystemId": "lubrication",
                "componentName": "Dry-Sump Lubrication & Filter",
                "health": 97.0,
                "status": "SCHEDULED PREVENTIVE",
                "priority": "ROUTINE",
                "badgeClass": "badge-healthy",
                "predictedIssue": "None. All telemetry nominal.",
                "recommendedAction": (
                    "Standard 50-hour oil and filter replacement; check magnetic chip detector for ferrous particles."
                ),
                "sparesRequired": "Rotax High-Flow Filter # 825-016, AeroShell Oil Sport Plus 4",
                "inspectionProcedure": "Inspect filter pleats; verify oil scavenge return flow rate.",
                "estServiceWindow": "At next 50-Hour turnaround",
                "estMTTR": "0.8 Hours",
                "postServiceReadiness": 98.8,
            })

        return orders

    def performVirtualMaintenance(self, subsystem_id):
        telemetryEngine.overhaulSubsystem(subsystem_id)
        if self.onOverhaulCompleted:
            try:
                self.onOverhaulCompleted(subsystem_id)
            except Exception as e:
                print("Error in onOverhaulCompleted:", e)

    def generatePrintableWorkOrder(self, order):
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return f"""
      <div class="printable-work-order">
        <div class="order-header">
          <div class="order-badge">OFFICIAL DEFENCE GCS WORK ORDER</div>
          <h2>GARUDAVYUHA PREDICTIVE MAINTENANCE SYSTEM</h2>
          <div class="order-meta">
            <span><strong>UAV:</strong> {ENGINE_CONFIG['uavPlatform']}</span>
            <span><strong>ENGINE:</strong> {ENGINE_CONFIG['modelName']}</span>
            <span><strong>WO#:</strong> {order['id']}</span>
            <span><strong>DATE:</strong> {now_utc} UTC</span>
          </div>
        </div>

        <div class="order-grid">
          <div class="order-field">
            <label>TARGET SUBSYSTEM:</label>
            <div class="val">{order['componentName']}</div>
          </div>
          <div class="order-field">
            <label>HEALTH SCORE:</label>
            <div class="val highlight-{order['badgeClass']}">{order['health']}% ({order['status']})</div>
          </div>
          <div class="order-field">
            <label>AI DIAGNOSIS / ISSUE:</label>
            <div class="val">{order['predictedIssue']}</div>
          </div>
          <div class="order-field">
            <label>SERVICE PRIORITY:</label>
            <div class="val">{order['priority']}</div>
          </div>
          <div class="order-field">
            <label>ESTIMATED MTTR:</label>
            <div class="val">{order['estMTTR']}</div>
          </div>
          <div class="order-field">
            <label>ESTIMATED SERVICE WINDOW:</label>
            <div class="val">{order['estServiceWindow']}</div>
          </div>
        </div>

        <div class="order-section">
          <h3>MANDATORY TECHNICAL ACTION PLAN:</h3>
          <p>{order['recommendedAction']}</p>
        </div>

        <div class="order-section">
          <h3>APPROVED SPARES & OEM PART NUMBERS:</h3>
          <p><code>{order['sparesRequired']}</code></p>
        </div>

        <div class="order-section">
          <h3>GROUND INSPECTION & COMPLIANCE PROCEDURE:</h3>
          <p>{order['inspectionProcedure']}</p>
        </div>

        <div class="order-footer">
          <div><strong>CHIEF AIRFRAME ENGINEER:</strong> ______________________</div>
          <div><strong>SIGN-OFF STATUS:</strong> [ PENDING INSPECTION ]</div>
        </div>
      </div>
    """


if __name__ == "__main__":
    mc = MaintenanceCenter()
    orders = mc.getWorkOrders({})
    print(f"Default Work Orders: {len(orders)}, First: {orders[0]['id']} ({orders[0]['componentName']})")
    html = mc.generatePrintableWorkOrder(orders[0])
    print(f"Generated Work Order HTML length: {len(html)} chars")
    print("MaintenanceCenter test passed!")
