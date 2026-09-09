"""
GARUDAVYUHA – 3D Digital Twin Engine Viewer
Loads and renders the Rotax 914 aero piston engine GLTF model
Interfaces with Three.js, OrbitControls, and GLTFLoader via Brython
"""

import math

try:
    from browser import window, document
    IN_BROWSER = True
except ImportError:
    window = None
    document = None
    IN_BROWSER = False


def js_new(cls, *args):
    if hasattr(cls, 'new'):
        return cls.new(*args)
    return cls(*args)


class DigitalTwin3D:
    def __init__(self, container_element, options=None):
        self.container = container_element
        self.options = options or {}

        self.scene = None
        self.camera = None
        self.renderer = None
        self.controls = None
        self.enginePivot = None
        self.engineModel = None
        self.loader = None

        self.allMeshes = []
        self.subsystemMeshes = {}
        self.originalMaterials = {}
        self.selectedSubsystem = 'fuel_injector'
        self.activeHighlightedSubsystem = 'fuel_injector'

        self.cameraTargetPos = None
        self.cameraLookAtTarget = None
        self.isCameraAnimating = False

        self.isThermalMode = False
        self.isWireframeMode = False
        self.showHotspots = True
        self.isPulsingCritical = True

        self.raycaster = None
        self.mouse = None

        self.onSelectComponent = self.options.get('onSelectComponent', None)
        self.clock = None
        self.animationFrameId = None

        if IN_BROWSER and window and hasattr(window, 'THREE'):
            self.init()

    def init(self):
        THREE = window.THREE
        OrbitControls = window.OrbitControls
        GLTFLoader = window.GLTFLoader

        width = getattr(self.container, 'clientWidth', 800) or 800
        height = getattr(self.container, 'clientHeight', 600) or 600

        # 1. Scene
        self.scene = js_new(THREE.Scene)
        self.scene.background = js_new(THREE.Color, 0x060b14)

        # 2. Camera
        self.camera = js_new(THREE.PerspectiveCamera, 40, width / height, 0.05, 50)
        self.camera.position.set(0.92, 0.52, 0.92)
        self.cameraTargetPos = js_new(THREE.Vector3, 0.92, 0.52, 0.92)
        self.cameraLookAtTarget = js_new(THREE.Vector3, 0, 0, 0)

        # 3. Renderer
        renderer_opts = window.Object.new()
        renderer_opts.antialias = True
        renderer_opts.powerPreference = "high-performance"
        renderer_opts.alpha = True

        self.renderer = js_new(THREE.WebGLRenderer, renderer_opts)
        self.renderer.setSize(width, height)
        pixel_ratio = min(getattr(window, 'devicePixelRatio', 1), 2)
        self.renderer.setPixelRatio(pixel_ratio)
        self.renderer.toneMapping = THREE.ACESFilmicToneMapping
        self.renderer.toneMappingExposure = 1.45
        self.renderer.shadowMap.enabled = True
        self.renderer.shadowMap.type = THREE.PCFSoftShadowMap
        self.container.appendChild(self.renderer.domElement)

        # 4. Controls
        self.controls = js_new(OrbitControls, self.camera, self.renderer.domElement)
        self.controls.enableDamping = True
        self.controls.dampingFactor = 0.06
        self.controls.minDistance = 0.35
        self.controls.maxDistance = 2.8
        self.controls.maxPolarAngle = math.pi / 2 + 0.08
        self.controls.target.set(0, 0, 0)

        # 5. Raycasting & Clock
        self.raycaster = js_new(THREE.Raycaster)
        self.mouse = js_new(THREE.Vector2)
        self.clock = js_new(THREE.Clock)
        self.loader = js_new(GLTFLoader)

        # 6. Lighting & Ground Radar Grid
        self.setupLighting()
        self.setupGroundGrid()

        # 7. Load 3D Model
        self.loadEngineModel()

        # 8. Event Listeners
        window.addEventListener('resize', lambda e: self.onWindowResize())
        self.renderer.domElement.addEventListener('pointermove', lambda e: self.onPointerMove(e))
        self.renderer.domElement.addEventListener('click', lambda e: self.onPointerClick(e))

        # 9. Start Render Loop
        self.animate()

    def setupLighting(self):
        THREE = window.THREE

        # Ambient fill
        ambient_light = js_new(THREE.AmbientLight, 0x1e293b, 2.2)
        self.scene.add(ambient_light)

        # Key Light
        key_light = js_new(THREE.DirectionalLight, 0xe0f2fe, 3.2)
        key_light.position.set(2.5, 4.5, 2.5)
        key_light.castShadow = True
        key_light.shadow.bias = -0.0004
        self.scene.add(key_light)

        # Cyan Rim Light
        cyan_rim = js_new(THREE.DirectionalLight, 0x00f0ff, 2.2)
        cyan_rim.position.set(-3.0, 2.0, -2.5)
        self.scene.add(cyan_rim)

        # Soft Fill
        fill_light = js_new(THREE.DirectionalLight, 0x94a3b8, 1.4)
        fill_light.position.set(1.5, 0.5, -2.0)
        self.scene.add(fill_light)

        # Warm Glow
        under_glow = js_new(THREE.PointLight, 0xf59e0b, 1.2, 3.0)
        under_glow.position.set(0.0, -0.4, 0.0)
        self.scene.add(under_glow)

    def setupGroundGrid(self):
        THREE = window.THREE
        radar_group = js_new(THREE.Group)
        radar_group.position.y = -0.28

        # Ring 1
        ring1_geo = js_new(THREE.RingGeometry, 0.45, 0.46, 64)
        ring1_mat_opts = window.Object.new()
        ring1_mat_opts.color = 0x00f0ff
        ring1_mat_opts.side = THREE.DoubleSide
        ring1_mat_opts.transparent = True
        ring1_mat_opts.opacity = 0.45
        ring1_mat = js_new(THREE.MeshBasicMaterial, ring1_mat_opts)
        ring1 = js_new(THREE.Mesh, ring1_geo, ring1_mat)
        ring1.rotation.x = math.pi / 2
        radar_group.add(ring1)

        # Ring 2
        ring2_geo = js_new(THREE.RingGeometry, 0.72, 0.73, 64)
        ring2_mat_opts = window.Object.new()
        ring2_mat_opts.color = 0x00f0ff
        ring2_mat_opts.side = THREE.DoubleSide
        ring2_mat_opts.transparent = True
        ring2_mat_opts.opacity = 0.3
        ring2_mat = js_new(THREE.MeshBasicMaterial, ring2_mat_opts)
        ring2 = js_new(THREE.Mesh, ring2_geo, ring2_mat)
        ring2.rotation.x = math.pi / 2
        radar_group.add(ring2)

        # Polar Grid
        polar_grid = js_new(THREE.PolarGridHelper, 0.9, 16, 6, 64, 0x00f0ff, 0x1e293b)
        polar_grid.material.opacity = 0.2
        polar_grid.material.transparent = True
        radar_group.add(polar_grid)

        self.scene.add(radar_group)

    def loadEngineModel(self):
        THREE = window.THREE
        loading_elem = document.getElementById('engine-3d-loading')
        if loading_elem:
            loading_elem.style.display = 'flex'

        print('[GARUDAVYUHA] Fetching Rotax 914 aero piston engine GLTF in Python...')

        def on_load(gltf):
            try:
                print('[GARUDAVYUHA] Rotax 914 GLTF loaded successfully via Python!')
                self.engineModel = gltf.scene

                box = js_new(THREE.Box3).setFromObject(self.engineModel)
                center = box.getCenter(js_new(THREE.Vector3))
                size = box.getSize(js_new(THREE.Vector3))

                self.enginePivot = js_new(THREE.Group)
                self.engineModel.position.set(-center.x, -center.y, -center.z)
                self.enginePivot.add(self.engineModel)

                self.enginePivot.rotation.x = -math.pi / 2
                self.enginePivot.rotation.z = math.pi / 3.4
                self.enginePivot.position.set(0, -0.02, 0)

                self.processMeshes()
                self.scene.add(self.enginePivot)

                if loading_elem:
                    loading_elem.style.display = 'none'

                self.highlightSubsystem('fuel_injector', 'critical', False)
            except Exception as err:
                print('[GARUDAVYUHA] Error processing loaded model:', err)
                if loading_elem:
                    loading_elem.innerHTML = f"<div style='color: #ef4444; padding: 20px; text-align: center;'>Error: {err}</div>"

        def on_progress(xhr):
            if hasattr(xhr, 'lengthComputable') and xhr.lengthComputable:
                pct = int(round((xhr.loaded / xhr.total) * 100))
                p_elem = document.getElementById('engine-loading-progress')
                if p_elem:
                    p_elem.textContent = f"{pct}%"

        def on_error(err):
            print('[GARUDAVYUHA] Network or Parsing Error loading Rotax914/Rotax 914.gltf:', err)
            if loading_elem:
                loading_elem.innerHTML = "<div style='color: #ef4444; padding: 20px;'>Failed to load Rotax 914 engine model.</div>"

        self.loader.load('Rotax914/Rotax%20914.gltf', on_load, on_progress, on_error)

    def processMeshes(self):
        THREE = window.THREE
        self.allMeshes = []
        comp_ids = [
            'cylinder_1', 'cylinder_2', 'cylinder_3', 'cylinder_4',
            'fuel_injector', 'ignition_system', 'oil_system',
            'cooling_system', 'exhaust_system', 'sensors'
        ]
        for cid in comp_ids:
            self.subsystemMeshes[cid] = []

        injector_mesh_indices = {44, 201, 246, 258, 263, 281, 291, 331, 359, 362}
        cyl1_indices = {21, 12, 20}
        cyl2_indices = {22, 13}
        cyl3_indices = {23, 17}
        cyl4_indices = {24, 25, 426}
        oil_indices = {10, 19, 14, 43}
        exhaust_indices = {15, 18, 9, 319}
        cooling_indices = {1, 16, 42}
        ignition_indices = {27, 28, 379}

        mesh_counter = 0

        def traverse_child(child):
            nonlocal mesh_counter
            if getattr(child, 'isMesh', False):
                child.castShadow = True
                child.receiveShadow = True
                self.allMeshes.append(child)
                idx = mesh_counter
                mesh_counter += 1
                child.userData.meshIndex = idx

                if hasattr(child, 'material') and child.material:
                    new_mat = self.enhanceMaterial(child.material)
                    child.material = new_mat
                    self.originalMaterials[idx] = new_mat

                comp_id = 'sensors'
                if idx in injector_mesh_indices:
                    comp_id = 'fuel_injector'
                elif idx in cyl4_indices:
                    comp_id = 'cylinder_4'
                elif idx in cyl3_indices:
                    comp_id = 'cylinder_3'
                elif idx in cyl2_indices:
                    comp_id = 'cylinder_2'
                elif idx in cyl1_indices:
                    comp_id = 'cylinder_1'
                elif idx in oil_indices:
                    comp_id = 'oil_system'
                elif idx in exhaust_indices:
                    comp_id = 'exhaust_system'
                elif idx in cooling_indices:
                    comp_id = 'cooling_system'
                elif idx in ignition_indices:
                    comp_id = 'ignition_system'

                self.subsystemMeshes[comp_id].append(child)
                child.userData.subsystemId = comp_id

        self.engineModel.traverse(traverse_child)
        print(f"[GARUDAVYUHA] Processed {len(self.allMeshes)} meshes. Components mapped.")

    def enhanceMaterial(self, mat):
        THREE = window.THREE
        new_mat = mat.clone()
        new_mat.roughness = 0.38
        new_mat.metalness = 0.72
        if not hasattr(new_mat, 'emissive') or not new_mat.emissive:
            new_mat.emissive = js_new(THREE.Color, 0x000000)
        new_mat.emissiveIntensity = 0
        return new_mat

    def highlightSubsystem(self, component_id, status='critical', animate_camera=False):
        self.activeHighlightedSubsystem = component_id

        primary_color = 0x10b981
        intensity = 0.6
        self.isPulsingCritical = False

        if status in ('warning', 'degrading'):
            primary_color = 0xf59e0b
            intensity = 1.0
        elif status == 'critical':
            primary_color = 0xf97316
            intensity = 1.65
            self.isPulsingCritical = True

        self.resetMeshHighlights()

        meshes = self.subsystemMeshes.get(component_id, [])
        for mesh in meshes:
            if hasattr(mesh, 'material') and mesh.material:
                mesh.material.emissive.setHex(primary_color)
                mesh.material.emissiveIntensity = intensity

        if animate_camera:
            self.focusCameraOnSubsystem(component_id)

    def resetMeshHighlights(self):
        for mesh in self.allMeshes:
            if hasattr(mesh, 'material') and mesh.material:
                mesh.material.emissive.setHex(0x000000)
                mesh.material.emissiveIntensity = 0
        self.isPulsingCritical = False

    def focusCameraOnSubsystem(self, component_id):
        THREE = window.THREE
        targets = {
            'fuel_injector': (js_new(THREE.Vector3, 0.55, 0.38, 0.55), js_new(THREE.Vector3, 0.05, 0.12, 0.08)),
            'cylinder_4': (js_new(THREE.Vector3, 0.65, 0.35, 0.45), js_new(THREE.Vector3, 0.08, 0.05, 0.05)),
            'cylinder_3': (js_new(THREE.Vector3, 0.55, 0.35, 0.65), js_new(THREE.Vector3, -0.08, 0.05, 0.05)),
            'cylinder_2': (js_new(THREE.Vector3, -0.55, 0.35, 0.65), js_new(THREE.Vector3, 0.08, -0.05, -0.05)),
            'cylinder_1': (js_new(THREE.Vector3, -0.65, 0.35, 0.45), js_new(THREE.Vector3, -0.08, -0.05, -0.05)),
            'oil_system': (js_new(THREE.Vector3, 0.45, -0.45, 0.65), js_new(THREE.Vector3, 0.0, -0.15, 0.0)),
            'exhaust_system': (js_new(THREE.Vector3, -0.75, 0.25, -0.65), js_new(THREE.Vector3, -0.15, 0.0, -0.1)),
            'cooling_system': (js_new(THREE.Vector3, 0.65, 0.25, -0.45), js_new(THREE.Vector3, 0.12, 0.0, 0.0)),
            'ignition_system': (js_new(THREE.Vector3, 0.35, 0.65, 0.45), js_new(THREE.Vector3, 0.0, 0.1, 0.0)),
            'sensors': (js_new(THREE.Vector3, 0.75, 0.45, 0.75), js_new(THREE.Vector3, 0, 0, 0)),
        }
        pos, look = targets.get(component_id, (js_new(THREE.Vector3, 0.92, 0.52, 0.92), js_new(THREE.Vector3, 0, 0, 0)))
        self.animateCameraTo(pos, look)

    def animateCameraTo(self, position, look_at_target):
        self.cameraTargetPos.copy(position)
        self.cameraLookAtTarget.copy(look_at_target)
        self.isCameraAnimating = True

    def setCameraPreset(self, preset_name):
        THREE = window.THREE
        presets = {
            'default': (js_new(THREE.Vector3, 0.92, 0.52, 0.92), js_new(THREE.Vector3, 0, 0, 0)),
            'front_prop': (js_new(THREE.Vector3, 0.95, 0.15, -0.15), js_new(THREE.Vector3, 0.15, 0.0, 0.0)),
            'turbo_exhaust': (js_new(THREE.Vector3, -0.85, -0.15, -0.65), js_new(THREE.Vector3, -0.18, 0.0, -0.1)),
            'cylinders_bank': (js_new(THREE.Vector3, 0.65, 0.45, 0.45), js_new(THREE.Vector3, 0.05, 0.05, 0.05)),
            'fuel_injection': (js_new(THREE.Vector3, 0.55, 0.42, 0.55), js_new(THREE.Vector3, 0.05, 0.12, 0.08)),
            'oil_sump': (js_new(THREE.Vector3, 0.35, -0.65, 0.45), js_new(THREE.Vector3, 0.0, -0.15, 0.0)),
            'top_down': (js_new(THREE.Vector3, 0.01, 1.35, 0.01), js_new(THREE.Vector3, 0, 0, 0)),
        }
        pos, target = presets.get(preset_name, presets['default'])
        self.animateCameraTo(pos, target)

    def toggleThermalMode(self, enable=None):
        self.isThermalMode = enable if enable is not None else not self.isThermalMode
        if self.isThermalMode:
            self.applyThermalShader()
        else:
            self.restoreOriginalMaterials()

    def applyThermalShader(self):
        for mesh in self.allMeshes:
            sub_id = mesh.userData.subsystemId
            temp_c = 92
            if sub_id == 'fuel_injector':
                temp_c = 780
            elif sub_id == 'exhaust_system':
                temp_c = 715
            elif sub_id in ('cylinder_4', 'cylinder_3'):
                temp_c = 142
            elif sub_id in ('cylinder_1', 'cylinder_2'):
                temp_c = 136
            elif sub_id == 'oil_system':
                temp_c = 96

            thermal_color = self.getThermalColor(temp_c)
            if hasattr(mesh, 'material') and mesh.material:
                mesh.material.color.copy(thermal_color)
                mesh.material.emissive.copy(thermal_color)
                mesh.material.emissiveIntensity = 0.9 if temp_c > 400 else 0.25

    def getThermalColor(self, temp_c):
        THREE = window.THREE
        if temp_c > 650:
            return js_new(THREE.Color, 0xfef08a)
        if temp_c > 450:
            return js_new(THREE.Color, 0xef4444)
        if temp_c > 200:
            return js_new(THREE.Color, 0xf97316)
        if temp_c > 130:
            return js_new(THREE.Color, 0xeab308)
        if temp_c > 90:
            return js_new(THREE.Color, 0x10b981)
        return js_new(THREE.Color, 0x06b6d4)

    def restoreOriginalMaterials(self):
        for mesh in self.allMeshes:
            idx = mesh.userData.meshIndex
            orig = self.originalMaterials.get(idx)
            if orig:
                mesh.material = orig
        if self.activeHighlightedSubsystem:
            self.highlightSubsystem(self.activeHighlightedSubsystem, 'critical', False)

    def toggleWireframe(self, enable=None):
        self.isWireframeMode = enable if enable is not None else not self.isWireframeMode
        for mesh in self.allMeshes:
            if hasattr(mesh, 'material') and mesh.material:
                mesh.material.wireframe = self.isWireframeMode

    def toggleAutoRotate(self, enable=None):
        if self.controls:
            self.controls.autoRotate = enable if enable is not None else not self.controls.autoRotate
            self.controls.autoRotateSpeed = 0.8

    def onPointerMove(self, event):
        rect = self.renderer.domElement.getBoundingClientRect()
        self.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
        self.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

    def onPointerClick(self, event):
        rect = self.renderer.domElement.getBoundingClientRect()
        self.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
        self.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

        self.raycaster.setFromCamera(self.mouse, self.camera)
        intersects = self.raycaster.intersectObjects(self.allMeshes, False)

        if intersects and len(intersects) > 0:
            hit_mesh = intersects[0].object
            sub_id = getattr(hit_mesh.userData, 'subsystemId', None)
            if sub_id:
                self.selectSubsystem(sub_id)

    def selectSubsystem(self, component_id):
        self.selectedSubsystem = component_id
        self.highlightSubsystem(component_id, 'critical', True)
        if self.onSelectComponent:
            try:
                self.onSelectComponent(component_id)
            except Exception as e:
                print("Error in onSelectComponent:", e)

    def onWindowResize(self):
        if not self.container or not self.renderer or not self.camera:
            return
        width = getattr(self.container, 'clientWidth', 0)
        height = getattr(self.container, 'clientHeight', 0)
        if width == 0 or height == 0:
            return
        self.camera.aspect = width / height
        self.camera.updateProjectionMatrix()
        self.renderer.setSize(width, height)

    def animate(self):
        window.requestAnimationFrame(lambda ts: self.animate())

        delta = self.clock.getDelta()
        curr_time = self.clock.getElapsedTime()

        # 1. Smooth Camera Lerp
        if self.isCameraAnimating:
            self.camera.position.lerp(self.cameraTargetPos, 0.07)
            self.controls.target.lerp(self.cameraLookAtTarget, 0.07)
            if self.camera.position.distanceTo(self.cameraTargetPos) < 0.01:
                self.isCameraAnimating = False

        # 2. Critical Pulsing Glow
        if self.isPulsingCritical and self.activeHighlightedSubsystem:
            pulse_intensity = 1.2 + math.sin(curr_time * 6.5) * 0.55
            meshes = self.subsystemMeshes.get(self.activeHighlightedSubsystem, [])
            for mesh in meshes:
                if hasattr(mesh, 'material') and mesh.material:
                    mesh.material.emissiveIntensity = pulse_intensity

        # 3. Render
        self.controls.update()
        self.renderer.render(self.scene, self.camera)


if __name__ == "__main__":
    print("DigitalTwin3D module defined. In browser mode:", IN_BROWSER)
