import copy,math,unittest
from aurora.labeling import fit,predict,vector

class LabelingTests(unittest.TestCase):
    def test_training_only_and_no_identity_features(self):
        p=[dict(piece_id='a',split='train',family_id='F1',width_mm=1,height_mm=2,area_mm2=1,relative_area=.2),dict(piece_id='b',split='test',family_id='F2',width_mm=3,height_mm=4,area_mm2=3,relative_area=.3)]
        labels={'a':{'standard_part_id':'EAR_LEFT'},'b':{'standard_part_id':'BODY_BACK'}}
        first=fit(p,labels,k=1);q=copy.deepcopy(p);q[1]['width_mm']=9999;labels['b']['standard_part_id']='TAIL'
        self.assertEqual(first,fit(q,labels,k=1));self.assertEqual(first['train_y'],['EAR']);self.assertNotIn('piece_id',first['features'])
        self.assertEqual(predict(first,vector(p[0]))['family'],'EAR')
    def test_invalid_dimensions(self):
        for v in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):vector(dict(width_mm=v,height_mm=1,area_mm2=1,relative_area=.1))
