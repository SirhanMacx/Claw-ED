class TestTeacherProfileValidation:
    def test_name_truncated_at_100(self):
        from clawed.models import TeacherProfile

        tp = TeacherProfile(name="A" * 150)
        assert len(tp.name) <= 100

    def test_name_stripped(self):
        from clawed.models import TeacherProfile

        tp = TeacherProfile(name="  Mr. Mac  ")
        assert tp.name == "Mr. Mac"

    def test_valid_subject_accepted(self):
        from clawed.models import TeacherProfile

        tp = TeacherProfile(subjects=["math"])
        assert "Math" in tp.subjects

    def test_fuzzy_subject_matched(self):
        from clawed.models import TeacherProfile

        tp = TeacherProfile(subjects=["social studies"])
        assert any("Social Studies" in s for s in tp.subjects)
