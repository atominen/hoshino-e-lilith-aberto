"""Admissão real com locks temporários; sem modelo, serviço ou GPU real."""
import fcntl
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from core import gpu_metrics, interentity as bus

GIB = 1024**3
ROOT = Path(__file__).resolve().parents[1]


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = patch.object(bus, 'DB_PATH', self.root/'presence.sqlite3')
        p.start(); self.addCleanup(p.stop)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('core.entity_admission'),
                             'Falta a admissão por capacidade antes de iniciar entidades')
        return importlib.import_module('core.entity_admission')

    def capacity(self, total):
        return patch.object(gpu_metrics, 'dedicated_capacity', create=True,
                            return_value=dict(known=total is not None, total_bytes=total))

    def test_single_entity_without_gpu_and_second_blocked_before_model_or_spawn(self):
        spec = importlib.util.spec_from_file_location('admission_launcher', ROOT/'iniciar_entidades.py')
        launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)
        bus.register('hoshino', 'awake', os.getpid())
        supervisor = launcher.Supervisor(laboratory_home=self.root/'absent')
        supervisor.project = self.root
        process = Mock(pid=os.getpid()); process.poll.return_value = None
        with self.capacity(8*GIB), patch.object(launcher, 'ROOT', self.root), \
             patch.object(launcher, 'validar_entidade', side_effect=lambda e:e), \
             patch('laboratorio.recuperacao_modelos.ensure', return_value={'state':'ready'}) as recover, \
             patch('core.neural9b_modes.startup_override', return_value=None), \
             patch.object(launcher.subprocess, 'Popen', return_value=process) as spawn:
            with self.assertRaisesRegex(ValueError, '16'):
                supervisor.start('lilith')
            recover.assert_not_called(); spawn.assert_not_called()
        self.assertEqual(bus.presence('hoshino')['status'], 'awake')

    def test_capacity_boundary_unknown_and_remote_entities_are_not_exempt(self):
        api = self.api()
        for total, permits_second in [(None,False),(8*GIB,False),(12*GIB,False),
                                      (15*GIB,False),(16*GIB-128*1024**2,False),
                                      (16*GIB-8*1024**2,True),(16*GIB,True),(24*GIB,True)]:
            with self.subTest(total=total), self.capacity(total):
                with api.instance(self.root,'alistair'):
                    if permits_second:
                        with api.instance(self.root,'lilith'): pass
                    else:
                        with self.assertRaisesRegex(ValueError,'16'):
                            with api.instance(self.root,'lilith'): pass

    def test_automatic_denial_preserves_wake_request_and_supervisor_tick(self):
        spec=importlib.util.spec_from_file_location('admission_tick',ROOT/'iniciar_entidades.py')
        launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        supervisor=launcher.Supervisor(laboratory_home=self.root/'absent');supervisor.project=self.root
        bus.register('hoshino','awake',os.getpid())
        request=bus.wake('hoshino','lilith')
        with self.capacity(8*GIB),patch.object(launcher,'validar_entidade',side_effect=lambda e:e):
            supervisor.tick()
        self.assertEqual(bus.pending_wake_requests()[0]['id'],request['id'])
        self.assertIn('16',supervisor.failures['lilith'])
        self.assertFalse(supervisor.processes)

    def test_real_runner_lock_blocks_even_without_fresh_presence(self):
        api = self.api()
        path = self.root/'entidades/hoshino/runtime/entity.lock'
        path.parent.mkdir(parents=True)
        with path.open('a+') as held, self.capacity(8*GIB):
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'16'):
                with api.instance(self.root,'lilith'): pass
        with self.capacity(None), api.instance(self.root,'lilith'): pass

    def test_bootstrap_inherited_lock_survives_preflight_and_is_adopted_by_runner(self):
        api=self.api(); path=self.root/'entidades/lilith/runtime/entity.boot.lock'
        path.parent.mkdir(parents=True)
        with path.open('a+') as boot, self.capacity(8*GIB), \
             patch.dict(os.environ,{'HOSHINO_ENTITY_LOCK_FD':str(boot.fileno())}):
            with api.boot(self.root,'lilith'):pass
            # Recuperação em processo separado ainda pode obter a trava de
            # manutenção; a admissão continua ocupada pela reserva de boot.
            with (path.parent/'entity.lock').open('a+') as recovery:
                fcntl.flock(recovery,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'16'):
                with api.guard(self.root,'hoshino'):pass
            with api.instance(self.root,'lilith'):pass

    def test_inherited_descriptor_of_other_entity_is_rejected(self):
        api=self.api(); path=self.root/'other.lock';path.touch()
        with path.open('r') as wrong,self.capacity(8*GIB), \
             patch.dict(os.environ,{'HOSHINO_ENTITY_LOCK_FD':str(wrong.fileno())}):
            with self.assertRaisesRegex(ValueError,'descritor'):
                with api.instance(self.root,'lilith'):pass

    def test_real_shell_keeps_boot_reservation_between_preflight_and_runner(self):
        self.api()
        helper=self.root/'preflight.py'
        helper.write_text("from pathlib import Path\nimport sys\nfrom core import entity_admission as a, interentity as b, gpu_metrics as g\n"
                          "root=Path(sys.argv[1]);b.DB_PATH=root/'bus.sqlite3'\n"
                          "g.dedicated_capacity=lambda:dict(known=False,total_bytes=None)\n"
                          "with (a.boot if sys.argv[3]=='boot' else a.instance)(root,sys.argv[2]):pass\n")
        for e in ('hoshino','lilith'):
            (self.root/'entidades'/e/'runtime').mkdir(parents=True)
        script=('exec 9>>"$1/entidades/$2/runtime/entity.boot.lock"; export HOSHINO_ENTITY_LOCK_FD=9; '
                '"$3" -B "$4" "$1" "$2" boot || exit $?; echo prepared; '
                'read -r finish; "$3" -B "$4" "$1" "$2" runner || exit $?; echo runner')
        cmd=lambda e:['bash','-c',script,'fixture',str(self.root),e,sys.executable,str(helper)]
        first=subprocess.Popen(cmd('hoshino'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(first.stdout.readline().strip(),'prepared')
            second=subprocess.run(cmd('lilith'),input='finish\n',capture_output=True,text=True,timeout=5)
            self.assertNotEqual(second.returncode,0)
            self.assertNotIn('prepared',second.stdout)
            self.assertIn('16 GB',second.stderr)
            out,err=first.communicate('finish\n',timeout=5)
            self.assertEqual(first.returncode,0,err);self.assertIn('runner',out)
        finally:
            if first.poll() is None:first.communicate('finish\n',timeout=5)

    def test_racing_starts_keep_one_slot_until_first_instance_exits(self):
        api = self.api()
        ready=threading.Barrier(2); release=threading.Event(); outcomes=[]
        def run(entity):
            ready.wait(timeout=3)
            try:
                with api.instance(self.root,entity):
                    outcomes.append('admitted'); release.wait(timeout=3)
            except ValueError:
                outcomes.append('blocked'); release.set()
        with self.capacity(8*GIB):
            workers=[threading.Thread(target=run,args=(e,)) for e in ('hoshino','lilith')]
            for worker in workers: worker.start()
            for worker in workers: worker.join(timeout=5)
        self.assertCountEqual(outcomes,['admitted','blocked'])
        self.assertTrue(all(not w.is_alive() for w in workers))

    def test_existing_managed_process_counts_and_duplicate_same_entity_stays_idempotent(self):
        api=self.api(); process=Mock(); process.poll.return_value=None
        with self.capacity(8*GIB):
            with self.assertRaisesRegex(ValueError,'16'):
                with api.guard(self.root,'lilith',processes={'hoshino':process}): pass
            with api.guard(self.root,'hoshino',processes={'hoshino':process}): pass

    def test_physical_capacity_is_not_the_rm_eight_gib_cap_or_sum_of_cards(self):
        self.assertTrue(hasattr(gpu_metrics,'dedicated_capacity'),'Falta sonda de capacidade física')
        for n,total in [(0,8*GIB),(1,8*GIB)]:
            device=self.root/f'card{n}/device'; device.mkdir(parents=True)
            (device/'vendor').write_text('0x1002')
            (device/'mem_info_vram_total').write_text(str(total))
        with patch('shutil.which', return_value=None):
            self.assertEqual(gpu_metrics.dedicated_capacity(self.root)['total_bytes'],8*GIB)
            (self.root/'card1/device/mem_info_vram_total').write_text(str(24*GIB))
            self.assertEqual(gpu_metrics.dedicated_capacity(self.root)['total_bytes'],24*GIB)

    def test_nvidia_capacity_and_unavailable_probe(self):
        self.assertTrue(hasattr(gpu_metrics,'dedicated_capacity'),'Falta sondaNVIDIA')
        reply=Mock(stdout='GPU-aaa, NVIDIA Test 16GB, 16376\nGPU-bbb, Other, 8192\n')
        with patch('shutil.which',return_value='/fixture/nvidia-smi'), \
             patch('subprocess.run',return_value=reply):
            found=gpu_metrics.dedicated_capacity(self.root)
            self.assertTrue(found['known']); self.assertEqual(found['total_bytes'],16376*1024**2)
        with patch('shutil.which',return_value=None):
            self.assertFalse(gpu_metrics.dedicated_capacity(self.root)['known'])


if __name__=='__main__':unittest.main()
