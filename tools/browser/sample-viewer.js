import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
export function createSampleViewer(host){
 let renderer,scene,camera,controls,object,token=0,currentBox;
 const fallback=message=>{host.dataset.ready='false';host.setAttribute('aria-label',message);};
 try{
  renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor('#eff3ef');renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.1;host.append(renderer.domElement);
  scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(35,1,.001,100);controls=new OrbitControls(camera,renderer.domElement);controls.enablePan=false;controls.addEventListener('change',render);scene.add(new THREE.HemisphereLight('#ffffff','#899b83',1.5));const light=new THREE.DirectionalLight('#fff4df',2);light.position.set(2,4,3);scene.add(light);const fill=new THREE.DirectionalLight('#cde7ef',1);fill.position.set(-2,1,-2);scene.add(fill);
  function resize(){const w=Math.max(host.clientWidth,1),h=Math.max(host.clientHeight,1);renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();render();}new ResizeObserver(resize).observe(host);resize();
 }catch(e){fallback('이 환경은 3D 표시를 지원하지 않습니다. 아래 2D 투영과 GLB 다운로드를 이용하세요.');host.textContent=host.getAttribute('aria-label');return {load:async()=>false,view:()=>{},clear:()=>{}};}
 function render(){if(renderer)renderer.render(scene,camera);}
 function dispose(model){model.traverse(n=>{if(n.geometry)n.geometry.dispose();for(const m of Array.isArray(n.material)?n.material:n.material?[n.material]:[]){for(const v of Object.values(m))if(v?.isTexture)v.dispose();m.dispose();}});}
 function view(side=false){if(!currentBox)return;const center=currentBox.getCenter(new THREE.Vector3()),size=currentBox.getSize(new THREE.Vector3());const r=Math.max(size.x,size.y,size.z)*1.45;camera.position.copy(center).add(side?new THREE.Vector3(r,.12*r,0):new THREE.Vector3(.9*r,.48*r,1.45*r));camera.near=r/100;camera.far=r*30;camera.updateProjectionMatrix();controls.target.copy(center);controls.update();render();}
 function clear(){token++;if(object){scene.remove(object);dispose(object);object=null;}currentBox=null;host.dataset.ready='false';render();}
 return {view,clear,async load(bytes){const mine=++token;try{const gltf=await new GLTFLoader().parseAsync(bytes,'');if(mine!==token){dispose(gltf.scene);return false;}if(object){scene.remove(object);dispose(object);}object=gltf.scene;object.traverse(n=>{if(n.isMesh&&!n.geometry.attributes.normal)n.geometry.computeVertexNormals();});scene.add(object);currentBox=new THREE.Box3().setFromObject(object);view();host.dataset.ready='true';host.setAttribute('aria-label','실제 GLB 3D 형상 · 드래그로 회전, 휠로 확대');return true;}catch(e){fallback('3D 파일 표시 실패. 2D 투영과 다운로드는 사용할 수 있습니다.');throw e;}}};
}
