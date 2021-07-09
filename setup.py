import setuptools

setuptools.setup(
    name="repo2docker-podman",
    # https://github.com/jupyter/repo2docker/pull/848
    install_requires=[
        "jupyter-repo2docker @ "
        "git+https://github.com/jupyterhub/repo2docker.git@master"
    ],
    python_requires=">=3.5",
    author="Simon Li",
    url="https://github.com/manics/repo2docker-podman",
    project_urls={"Documentation": "https://repo2docker.readthedocs.io"},
    keywords="reproducible science environments docker",
    description="Repo2docker Podman extension",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    use_scm_version={"write_to": "repo2podman/_version.py"},
    setup_requires=["setuptools_scm"],
    license="BSD",
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
    packages=setuptools.find_packages(),
    include_package_data=True,
    entry_points={"repo2docker.engines": ["podman = repo2podman.podman:PodmanEngine"]},
)
